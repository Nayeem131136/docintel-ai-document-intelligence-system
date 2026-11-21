import { vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Profile from "../pages/Profile";
import { AuthProvider } from "../lib/auth";

const STATS = {
  documents: { total: 5, by_status: {} },
  processing: { success_rate: 0.8, failure_rate: 0.2, avg_time_ms: 2500 },
  invoices: { total: 7, needs_review: 2 },
  open_issues: 3,
};

function renderProfile() {
  localStorage.setItem("docintel.token", "secret-token-123");
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const body = String(url).includes("/stats/") ? STATS : { username: "alice", is_staff: true };
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><AuthProvider><Profile /></AuthProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("<Profile>", () => {
  it("shows the account and usage", async () => {
    renderProfile();
    expect(await screen.findByText("alice")).toBeInTheDocument();
    expect(screen.getByText("Staff account")).toBeInTheDocument();
    expect(await screen.findByText("80%")).toBeInTheDocument();
    expect(screen.getByText("Invoices needing review").nextSibling).toHaveTextContent("2");
  });

  it("hides the API token until asked", async () => {
    renderProfile();
    const token = await screen.findByTestId("token");
    expect(token).not.toHaveTextContent("secret-token-123");
    await userEvent.click(screen.getByRole("button", { name: /show/i }));
    expect(token).toHaveTextContent("secret-token-123");
    await userEvent.click(screen.getByRole("button", { name: /hide/i }));
    expect(token).not.toHaveTextContent("secret-token-123");
  });
});
