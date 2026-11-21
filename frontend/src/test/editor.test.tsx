
import { vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import InvoiceEditor, {
  buildPayload,
  toForm,
  validateForm,
} from "../components/InvoiceEditor";
import { ToastProvider } from "../lib/toast";
import type { Invoice } from "../lib/types";

const invoice: Invoice = {
  id: 7,
  document: "d1",
  filename: "a.pdf",
  page_start: 1,
  page_end: 1,
  invoice_number: "INV-1",
  invoice_date: "2025-03-01",
  supplier_name: "Acme",
  customer_name: "Globex",
  currency: "USD",
  subtotal: "175.00",
  discount: "-10.00",
  tax: "17.50",
  total: "182.50",
  line_items: [
    {
      description: "Widget",
      quantity: "2",
      unit_price: "50",
      amount: "100",
    },
  ],
  confidence: { total: 0.9 },
  method: "llm",
  model_name: "m",
  review_status: "needs_review",
  corrections: [],
  created_at: "",
  updated_at: "t1",
  issues: [
    {
      id: 1,
      code: "TOTAL_MISMATCH",
      severity: "error",
      field: "total",
      message: "Total does not match.",
      expected: "182.50",
      found: "200.00",
      resolved: false,
      created_at: "",
    },
  ],
};

describe("buildPayload", () => {
  it("sends only the fields that changed", () => {
    const initial = toForm(invoice);

    expect(buildPayload(initial, initial, false)).toEqual({});

    expect(
      buildPayload(
        { ...initial, total: "190.00", note: "typo" },
        initial,
        false,
      ),
    ).toEqual({
      total: "190.00",
      note: "typo",
    });
  });

  it("sends discount when it changes", () => {
    const initial = toForm(invoice);

    expect(
      buildPayload(
        { ...initial, discount: "-15.00" },
        initial,
        false,
      ),
    ).toEqual({
      discount: "-15.00",
    });
  });

  it("turns cleared fields into null", () => {
    const initial = toForm(invoice);

    expect(
      buildPayload(
        { ...initial, supplier_name: "  " },
        initial,
        false,
      ),
    ).toEqual({
      supplier_name: null,
    });
  });

  it("includes line items only when they changed, dropping blank rows", () => {
    const initial = toForm(invoice);

    const changed = {
      ...initial,
      line_items: [
        ...initial.line_items,
        {
          description: "",
          quantity: "",
          unit_price: "",
          amount: "",
        },
      ],
    };

    expect(buildPayload(changed, initial, false)).toEqual({});

    const edited = {
      ...initial,
      line_items: [
        {
          ...initial.line_items[0],
          amount: "110",
        },
      ],
    };

    expect(
      buildPayload(edited, initial, false).line_items?.[0].amount,
    ).toBe("110");
  });

  it("on create only sends what was filled in", () => {
    const blank = toForm(null);

    expect(
      buildPayload(
        {
          ...blank,
          invoice_number: "M-1",
          total: "10.00",
        },
        blank,
        true,
      ),
    ).toEqual({
      invoice_number: "M-1",
      total: "10.00",
    });
  });
});

describe("validateForm", () => {
  it("flags bad currency, money and line item numbers", () => {
    const form = {
      ...toForm(invoice),
      currency: "DOLLARS",
      total: "12.345",
      line_items: [
        {
          description: "x",
          quantity: "abc",
          unit_price: "",
          amount: "",
        },
      ],
    };

    const errors = validateForm(form);

    expect(errors.currency).toBeDefined();
    expect(errors.total).toBeDefined();
    expect(errors["line_items.0.quantity"]).toBeDefined();
    expect(validateForm(toForm(invoice))).toEqual({});
  });

  it("validates discount as a money field", () => {
    const form = {
      ...toForm(invoice),
      discount: "-10.999",
    };

    expect(validateForm(form).discount).toBeDefined();

    const validForm = {
      ...toForm(invoice),
      discount: "-10.00",
    };

    expect(validateForm(validForm).discount).toBeUndefined();
  });
});

describe("<InvoiceEditor>", () => {
  function setup(fetchImpl: typeof fetch) {
    vi.stubGlobal("fetch", fetchImpl);

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <InvoiceEditor documentId="d1" invoice={invoice} />
        </ToastProvider>
      </QueryClientProvider>,
    );
  }

  afterEach(() => vi.unstubAllGlobals());

  it("shows issues, keeps Save disabled until something changes, then saves only the change", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ...invoice,
          total: "190.00",
          updated_at: "t2",
        }),
        { status: 200 },
      ),
    );

    setup(fetchMock as unknown as typeof fetch);

    expect(screen.getByText("Total mismatch")).toBeInTheDocument();

    const save = screen.getByRole("button", {
      name: /save changes/i,
    });

    expect(save).toBeDisabled();

    const total = screen.getByLabelText("Total");

    await userEvent.clear(total);
    await userEvent.type(total, "190.00");

    expect(save).toBeEnabled();

    await userEvent.click(save);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const [url, init] = fetchMock.mock.calls[0];

    expect(url).toBe("/api/results/7/");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({
      total: "190.00",
    });
  });

  it("blocks saving an invalid currency and explains why", async () => {
    setup(vi.fn() as unknown as typeof fetch);

    const currency = screen.getByLabelText("Currency");

    await userEvent.clear(currency);
    await userEvent.type(currency, "XX");

    expect(
      screen.getByText(/3-letter code/),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: /save changes/i }),
    ).toBeDisabled();
  });

  it("displays the discount field", () => {
    setup(vi.fn() as unknown as typeof fetch);

    expect(screen.getByLabelText("Discount")).toHaveValue("-10.00");
  });
});

describe("number display", () => {
  it("hides trailing zeros of quantities and unit prices", () => {
    const form = toForm({
      ...invoice,
      line_items: [
        {
          description: "x",
          quantity: "2.0000",
          unit_price: "50.5000",
          amount: "101.00",
        },
      ],
    });

    expect(form.line_items[0]).toMatchObject({
      quantity: "2",
      unit_price: "50.5",
      amount: "101.00",
    });
  });
});
