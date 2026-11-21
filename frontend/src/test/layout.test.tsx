import { vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import Layout, { titleFor } from "../components/Layout";
import { AuthProvider } from "../lib/auth";

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

function mockServer(healthy: boolean) {
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (String(url).includes("/health/")) return Promise.resolve(new Response("{}", { status: healthy ? 200 : 503 }));
    return Promise.resolve(new Response(JSON.stringify({ username: "alice", is_staff: false }), { status: 200 }));
  }));
}

function renderLayout(path = "/documents") {
  localStorage.setItem("docintel.token", "tok");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route path="*" element={<Where />} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("titleFor", () => {
  it("names the current page", () => {
    expect(titleFor("/")).toBe("Dashboard");
    expect(titleFor("/documents")).toBe("Documents");
    expect(titleFor("/documents/abc")).toBe("Document");
    expect(titleFor("/search")).toBe("Search");
    expect(titleFor("/profile")).toBe("Profile");
    expect(titleFor("/nope")).toBe("DocIntel");
  });
});

describe("<Layout> header and footer", () => {
  it("shows the page title, the user, the API status and a footer", async () => {
    mockServer(true);
    renderLayout("/invoices");
    expect(screen.getByTestId("page-title")).toHaveTextContent("Invoices");
    expect(await screen.findByText("alice", { selector: "p.max-w-\\[9rem\\]" })).toBeInTheDocument();
    expect(await screen.findByText("API online")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent(/Always review extracted values/);
  });

  it("says so when the API cannot be reached", async () => {
    mockServer(false);
    renderLayout();
    expect(await screen.findByText("API offline")).toBeInTheDocument();
  });

  it("links the user chip to the profile page", async () => {
    mockServer(true);
    renderLayout();
    await userEvent.click(await screen.findByRole("link", { name: "Your profile" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/profile");
  });

  it("sends the quick search to the search page", async () => {
    mockServer(true);
    renderLayout();
    await screen.findByText("API online");
    await userEvent.type(screen.getByLabelText("Quick search"), "printing services{Enter}");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/search?q=printing%20services"));
  });

  it("signs the user out from the header", async () => {
    mockServer(true);
    renderLayout();
    await userEvent.click(within(await screen.findByRole("banner")).getByRole("button", { name: "Sign out" }));
    expect(localStorage.getItem("docintel.token")).toBeNull();
  });
});
