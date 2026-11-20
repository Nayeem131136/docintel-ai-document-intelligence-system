
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, ChevronDown, History, Plus, Save, Trash2, Wand2 } from "lucide-react";
import { ApiError, api } from "../lib/api";
import { formatDateTime, issueLabel, SEVERITY_TONE } from "../lib/format";
import { useToast } from "../lib/toast";
import type { Invoice, InvoiceWrite, Issue, LineItem } from "../lib/types";
import { ReviewBadge } from "./StatusBadge";
import { Badge, Button, cx } from "./ui";

type Scalar =
  | "invoice_number"
  | "invoice_date"
  | "supplier_name"
  | "customer_name"
  | "currency"
  | "subtotal"
  | "discount"
  | "tax"
  | "total";

export interface FormState {
  invoice_number: string;
  invoice_date: string;
  supplier_name: string;
  customer_name: string;
  currency: string;
  subtotal: string;
  discount: string;
  tax: string;
  total: string;
  line_items: {
    description: string;
    quantity: string;
    unit_price: string;
    amount: string;
  }[];
  note: string;
}

const FIELDS: {
  key: Scalar;
  label: string;
  type?: string;
  wide?: boolean;
}[] = [
  { key: "invoice_number", label: "Invoice number" },
  { key: "invoice_date", label: "Invoice date", type: "date" },
  { key: "supplier_name", label: "Supplier", wide: true },
  { key: "customer_name", label: "Customer", wide: true },
  { key: "currency", label: "Currency" },
  { key: "subtotal", label: "Subtotal" },
  { key: "discount", label: "Discount" },
  { key: "tax", label: "Tax" },
  { key: "total", label: "Total" },
];

const SCALARS: Scalar[] = FIELDS.map((f) => f.key);
const MONEY = ["subtotal", "discount", "tax", "total"];

const s = (v: string | null | undefined) => v ?? "";

/** Remove unnecessary trailing zeros from decimal values. */
const plain = (v: string | null | undefined) =>
  v && v.includes(".")
    ? v.replace(/0+$/, "").replace(/\.$/, "")
    : s(v);

export function toForm(invoice: Invoice | null): FormState {
  return {
    invoice_number: s(invoice?.invoice_number),
    invoice_date: s(invoice?.invoice_date),
    supplier_name: s(invoice?.supplier_name),
    customer_name: s(invoice?.customer_name),
    currency: s(invoice?.currency),
    subtotal: s(invoice?.subtotal),
    discount: s(invoice?.discount),
    tax: s(invoice?.tax),
    total: s(invoice?.total),

    line_items: (invoice?.line_items ?? []).map((i) => ({
      description: s(i.description),
      quantity: plain(i.quantity),
      unit_price: plain(i.unit_price),
      amount: s(i.amount),
    })),

    note: "",
  };
}

const emptyToNull = (v: string) =>
  v.trim() === "" ? null : v.trim();

const trimZeros = (v: string) =>
  v.includes(".")
    ? v.replace(/0+$/, "").replace(/\.$/, "")
    : v;

/** Build the PATCH body: only fields that changed. */
export function buildPayload(
  form: FormState,
  initial: FormState,
  creating: boolean,
): InvoiceWrite {
  const payload: Record<string, unknown> = {};

  for (const key of SCALARS) {
    if (
      form[key] !== initial[key] &&
      (creating ? form[key].trim() !== "" : true)
    ) {
      payload[key] = emptyToNull(form[key]);
    }
  }

  const rows = (items: FormState["line_items"]) =>
    items.filter((i) =>
      Object.values(i).some((v) => v.trim() !== ""),
    );

  const before = JSON.stringify(rows(initial.line_items));
  const after = JSON.stringify(rows(form.line_items));

  if (before !== after) {
    payload.line_items = rows(form.line_items).map<LineItem>((i) => ({
      description: emptyToNull(i.description),
      quantity: emptyToNull(i.quantity),
      unit_price: emptyToNull(i.unit_price),
      amount: emptyToNull(i.amount),
    }));
  }

  if (form.note.trim() && Object.keys(payload).length) {
    payload.note = form.note.trim();
  }

  return payload as InvoiceWrite;
}

/** Client-side validation. */
export function validateForm(
  form: FormState,
): Record<string, string> {
  const errors: Record<string, string> = {};

  if (
    form.currency.trim() &&
    !/^[A-Za-z]{3}$/.test(form.currency.trim())
  ) {
    errors.currency = "Use a 3-letter code such as USD.";
  }

  for (const key of MONEY) {
    const v = form[key as Scalar].trim();

    if (v && !/^-?\d+(\.\d{1,2})?$/.test(v)) {
      errors[key] = "Use a number with at most 2 decimals.";
    }
  }

  if (form.invoice_number.length > 100) {
    errors.invoice_number = "Too long (max 100).";
  }

  form.line_items.forEach((row, index) => {
    for (const key of [
      "quantity",
      "unit_price",
      "amount",
    ] as const) {
      const v = row[key].trim();

      if (v && !/^-?\d+(\.\d+)?$/.test(v)) {
        errors[`line_items.${index}.${key}`] =
          "Not a number.";
      }
    }
  });

  return errors;
}

function IssueRow({
  issue,
  onResolve,
  busy,
}: {
  issue: Issue;
  onResolve: (id: number) => void;
  busy: boolean;
}) {
  return (
    <li
      className={cx(
        "flex items-start gap-3 rounded-lg border p-3 text-sm",
        issue.resolved
          ? "border-slate-200 bg-slate-50 opacity-70"
          : issue.severity === "error"
            ? "border-red-200 bg-red-50/60"
            : "border-amber-200 bg-amber-50/60",
      )}
    >
      <Badge
        tone={
          issue.resolved
            ? "slate"
            : SEVERITY_TONE[issue.severity]
        }
      >
        {issue.resolved ? "Resolved" : issue.severity}
      </Badge>

      <div className="min-w-0 flex-1">
        <p className="font-medium text-slate-800">
          {issueLabel(issue.code)}
          {issue.field && (
            <span className="font-normal text-slate-500">
              {" "} - {issue.field}
            </span>
          )}
        </p>

        <p className="text-slate-600">{issue.message}</p>

        {(issue.expected || issue.found) && (
          <p className="mt-0.5 text-xs text-slate-500">
            {issue.expected && (
              <>
                Expected <b>{issue.expected}</b>{" "}
              </>
            )}
            {issue.found && (
              <>
                found <b>{issue.found}</b>
              </>
            )}
          </p>
        )}
      </div>

      {!issue.resolved && issue.severity !== "info" && (
        <Button
          small
          disabled={busy}
          onClick={() => onResolve(issue.id)}
          title="Mark this issue as checked and acceptable"
        >
          Accept
        </Button>
      )}
    </li>
  );
}

interface Props {
  documentId: string;
  invoice: Invoice | null;
  onDone?: () => void;
}

export default function InvoiceEditor({
  documentId,
  invoice,
  onDone,
}: Props) {
  const creating = invoice === null;

  const initial = useMemo(
    () => toForm(invoice),
    [invoice],
  );

  const [form, setForm] = useState<FormState>(initial);
  const [serverErrors, setServerErrors] = useState<
    Record<string, string>
  >({});
  const [showHistory, setShowHistory] = useState(false);

  const queryClient = useQueryClient();
  const { notify } = useToast();

  // Reset the form when the server sends a new invoice version.
  const [seen, setSeen] = useState(invoice?.updated_at);

  if (invoice && invoice.updated_at !== seen) {
    setSeen(invoice.updated_at);
    setForm(toForm(invoice));
    setServerErrors({});
  }

  const clientErrors = useMemo(
    () => validateForm(form),
    [form],
  );

  const errors = {
    ...serverErrors,
    ...clientErrors,
  };

  const payload = useMemo(
    () => buildPayload(form, initial, creating),
    [form, initial, creating],
  );

  const dirty = Object.keys(payload).length > 0;

  const refresh = () => {
    for (const key of [
      "results",
      "documents",
      "stats",
      "invoices",
      "docstatus",
    ]) {
      queryClient.invalidateQueries({
        queryKey: [key],
      });
    }
  };

  const onError = (e: unknown) => {
    if (e instanceof ApiError && e.status === 400) {
      setServerErrors(e.fieldErrors);
    }

    notify(
      "error",
      e instanceof Error
        ? e.message
        : "Something went wrong.",
    );
  };

  const save = useMutation({
    mutationFn: () =>
      creating
        ? api.createInvoice(documentId, payload)
        : api.updateInvoice(invoice!.id, payload),

    onSuccess: () => {
      notify(
        "success",
        creating
          ? "Invoice added."
          : "Changes saved and re-validated.",
      );

      setServerErrors({});
      refresh();
      onDone?.();
    },

    onError,
  });

  const approve = useMutation({
    mutationFn: () => api.approveInvoice(invoice!.id),

    onSuccess: () => {
      notify("success", "Invoice marked as reviewed.");
      refresh();
    },

    onError,
  });

  const resolve = useMutation({
    mutationFn: (id: number) => api.resolveIssue(id),

    onSuccess: () => {
      refresh();
    },

    onError,
  });

  const openIssues = (invoice?.issues ?? []).filter(
    (i) => !i.resolved && i.severity !== "info",
  );

  const fieldTone = (key: string) => {
    if (errors[key]) return "input-error";

    const issue = openIssues.find(
      (i) => i.field === key,
    );

    return issue
      ? issue.severity === "error"
        ? "input-error"
        : "border-amber-400 focus:border-amber-500 focus:ring-amber-400/30"
      : "";
  };

  const setField = (key: Scalar, value: string) => {
    setForm((f) => ({
      ...f,
      [key]: value,
    }));

    setServerErrors((e) => ({
      ...e,
      [key]: "",
    }));
  };

  const setRow = (
    index: number,
    key: keyof FormState["line_items"][number],
    value: string,
  ) => {
    setForm((f) => ({
      ...f,
      line_items: f.line_items.map((r, i) =>
        i === index
          ? { ...r, [key]: value }
          : r,
      ),
    }));
  };

  const hasClientErrors = Object.values(
    clientErrors,
  ).some(Boolean);

  return (
    <div className="card animate-fade-up overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/60 px-5 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold text-brand-900">
            {creating
              ? "Add invoice manually"
              : invoice.invoice_number
                ? `Invoice ${invoice.invoice_number}`
                : "Invoice (no number found)"}
          </h3>

          {!creating && (
            <ReviewBadge status={invoice.review_status} />
          )}

          {!creating && (
            <Badge
              tone={
                invoice.method === "llm"
                  ? "accent"
                  : invoice.method === "manual"
                    ? "blue"
                    : "slate"
              }
            >
              <Wand2 className="h-3 w-3" />
              {" "}
              {invoice.method === "llm"
                ? "AI extracted"
                : invoice.method === "rules"
                  ? "Rule-based"
                  : "Manual"}
            </Badge>
          )}

          {!creating && invoice.page_start && (
            <span className="text-xs text-slate-500">
              {invoice.page_end &&
              invoice.page_end !== invoice.page_start
                ? `Pages ${invoice.page_start}-${invoice.page_end}`
                : `Page ${invoice.page_start}`}
            </span>
          )}
        </div>

        {!creating &&
          invoice.review_status !== "reviewed" && (
            <Button
              small
              variant="secondary"
              icon={<CheckCheck className="h-4 w-4" />}
              loading={approve.isPending}
              onClick={() => approve.mutate()}
              title="Confirm the values are correct as they are"
            >
              Approve as correct
            </Button>
          )}
      </div>

      <div className="space-y-5 p-5">
        {!creating && invoice.issues.length > 0 && (
          <ul
            className="space-y-2"
            aria-label="Validation issues"
          >
            {invoice.issues.map((issue) => (
              <IssueRow
                key={issue.id}
                issue={issue}
                busy={resolve.isPending}
                onResolve={(id) => resolve.mutate(id)}
              />
            ))}
          </ul>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FIELDS.map(({ key, label, type, wide }) => {
            const confidence = invoice?.confidence?.[key];

            return (
              <div
                key={key}
                className={wide ? "sm:col-span-2" : ""}
              >
                <label
                  className="label"
                  htmlFor={`f-${invoice?.id ?? "new"}-${key}`}
                >
                  {label}
                </label>

                <input
                  id={`f-${invoice?.id ?? "new"}-${key}`}
                  type={type ?? "text"}
                  className={cx("input", fieldTone(key))}
                  value={form[key]}
                  inputMode={
                    MONEY.includes(key)
                      ? "decimal"
                      : undefined
                  }
                  placeholder={
                    creating ? "" : "Not found"
                  }
                  title={
                    typeof confidence === "number"
                      ? `Model confidence ${Math.round(confidence * 100)}%`
                      : undefined
                  }
                  onChange={(e) =>
                    setField(key, e.target.value)
                  }
                />

                {errors[key] && (
                  <p className="mt-1 text-xs text-red-600">
                    {errors[key]}
                  </p>
                )}
              </div>
            );
          })}
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="label !mb-0">Line items</p>

            <Button
              small
              icon={<Plus className="h-3.5 w-3.5" />}
              onClick={() =>
                setForm((f) => ({
                  ...f,
                  line_items: [
                    ...f.line_items,
                    {
                      description: "",
                      quantity: "",
                      unit_price: "",
                      amount: "",
                    },
                  ],
                }))
              }
            >
              Add row
            </Button>
          </div>

          {form.line_items.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-300 px-3 py-4 text-center text-sm text-slate-500">
              No line items.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="pb-1 pr-2 font-medium">
                      Description
                    </th>
                    <th className="w-24 pb-1 pr-2 font-medium">
                      Qty
                    </th>
                    <th className="w-28 pb-1 pr-2 font-medium">
                      Unit price
                    </th>
                    <th className="w-28 pb-1 pr-2 font-medium">
                      Amount
                    </th>
                    <th className="w-8" />
                  </tr>
                </thead>

                <tbody>
                  {form.line_items.map((row, index) => (
                    <tr key={index}>
                      <td className="pb-2 pr-2">
                        <input
                          aria-label={`Item ${index + 1} description`}
                          className="input"
                          value={row.description}
                          onChange={(e) =>
                            setRow(
                              index,
                              "description",
                              e.target.value,
                            )
                          }
                        />
                      </td>

                      {(
                        [
                          "quantity",
                          "unit_price",
                          "amount",
                        ] as const
                      ).map((key) => (
                        <td
                          key={key}
                          className="pb-2 pr-2"
                        >
                          <input
                            aria-label={`Item ${index + 1} ${key.replace("_", " ")}`}
                            className={cx(
                              "input",
                              errors[
                                `line_items.${index}.${key}`
                              ] && "input-error",
                            )}
                            inputMode="decimal"
                            value={row[key]}
                            onChange={(e) =>
                              setRow(
                                index,
                                key,
                                e.target.value,
                              )
                            }
                          />
                        </td>
                      ))}

                      <td className="pb-2">
                        <button
                          aria-label={`Remove item ${index + 1}`}
                          className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500"
                          onClick={() =>
                            setForm((f) => ({
                              ...f,
                              line_items: f.line_items.filter(
                                (_, i) => i !== index,
                              ),
                            }))
                          }
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {errors.line_items && (
            <p className="mt-1 text-xs text-red-600">
              {errors.line_items}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-3 border-t border-slate-100 pt-4">
          <div className="min-w-[14rem] flex-1">
            <label
              className="label"
              htmlFor={`note-${invoice?.id ?? "new"}`}
            >
              Note (optional, saved in the audit trail)
            </label>

            <input
              id={`note-${invoice?.id ?? "new"}`}
              className="input"
              value={form.note}
              placeholder="Why are you changing this?"
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  note: e.target.value,
                }))
              }
            />
          </div>

          {dirty && (
            <Button
              variant="ghost"
              onClick={() => {
                setForm(initial);
                setServerErrors({});
              }}
            >
              Discard
            </Button>
          )}

          <Button
            variant="primary"
            icon={<Save className="h-4 w-4" />}
            loading={save.isPending}
            disabled={!dirty || hasClientErrors}
            onClick={() => save.mutate()}
          >
            {creating ? "Add invoice" : "Save changes"}
          </Button>
        </div>

        {!creating && invoice.corrections.length > 0 && (
          <div>
            <button
              className="flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-brand-900"
              onClick={() =>
                setShowHistory((v) => !v)
              }
              aria-expanded={showHistory}
            >
              <History className="h-4 w-4" />
              {" "}
              Change history ({invoice.corrections.length})
              <ChevronDown
                className={cx(
                  "h-4 w-4 transition",
                  showHistory && "rotate-180",
                )}
              />
            </button>

            {showHistory && (
              <ul className="mt-2 space-y-1.5 text-sm">
                {invoice.corrections.map((c) => (
                  <li
                    key={c.id}
                    className="rounded-lg bg-slate-50 px-3 py-2"
                  >
                    <span className="font-medium">
                      {c.field}
                    </span>
                    :{" "}
                    <span className="text-red-600 line-through">
                      {trimZeros(c.old_value) || "empty"}
                    </span>
                    {" -> "}
                    <span className="text-emerald-700">
                      {trimZeros(c.new_value) || "empty"}
                    </span>

                    <span className="ml-2 text-xs text-slate-400">
                      {formatDateTime(c.corrected_at)}
                    </span>

                    {c.note && (
                      <span className="block text-xs text-slate-500">
                        {c.note}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
