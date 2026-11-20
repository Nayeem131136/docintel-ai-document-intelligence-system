import { vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Highlight from "../components/Highlight";
import UploadZone from "../components/UploadZone";
import { AuthProvider } from "../lib/auth";
import { ToastProvider } from "../lib/toast";
import Login from "../pages/Login";

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}><MemoryRouter><AuthProvider><ToastProvider>{ui}</ToastProvider></AuthProvider></MemoryRouter></QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("<Login>", () => {
  it("shows the server message when credentials are wrong", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ non_field_errors: ["Unable to log in with provided credentials."] }), { status: 400 })));
    wrap(<Login />);
    await userEvent.type(screen.getByLabelText("Username"), "alice");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Unable to log in/);
    expect(localStorage.getItem("docintel.token")).toBeNull();
  });
  it("stores the token after a successful login", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ token: "tok", username: "alice", is_staff: false }), { status: 200 })));
    wrap(<Login />);
    await userEvent.type(screen.getByLabelText("Username"), "alice");
    await userEvent.type(screen.getByLabelText("Password"), "right");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(localStorage.getItem("docintel.token")).toBe("tok"));
  });
});

describe("<UploadZone>", () => {
  it("rejects unsupported files immediately without calling the server", async () => {
    const send = vi.fn();
    vi.stubGlobal("XMLHttpRequest", vi.fn(() => ({ open: vi.fn(), send, setRequestHeader: vi.fn(), upload: {} })));
    wrap(<UploadZone />);
    const input = screen.getByTestId("file-input");
    fireEvent.change(input, { target: { files: [new File(["x"], "notes.docx")] } });
    expect(await screen.findByText(/Unsupported type/)).toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });
  it("uploads each valid file and reports completion", async () => {
    const instances: { onload?: () => void; status: number; responseText: string }[] = [];
    vi.stubGlobal("XMLHttpRequest", vi.fn(function (this: Record<string, unknown>) {
      Object.assign(this, { open: vi.fn(), setRequestHeader: vi.fn(), upload: {}, status: 202, responseText: "{\"documents\":[],\"rejected\":[]}",
        send: () => setTimeout(() => (this.onload as () => void)(), 0) });
      instances.push(this as never);
    }));
    const done = vi.fn();
    wrap(<UploadZone onUploaded={done} />);
    fireEvent.change(screen.getByTestId("file-input"), { target: { files: [new File(["%PDF"], "a.pdf"), new File(["x,y"], "b.csv")] } });
    await waitFor(() => expect(screen.getAllByText(/Uploaded - processing in the background/)).toHaveLength(2));
    expect(done).toHaveBeenCalledTimes(2);
  });
});

describe("<Highlight>", () => {
  it("marks matches case-insensitively and never renders HTML", () => {
    const { container } = render(<Highlight text={'Acme <b>Ltd</b> acme'} terms={["acme"]} />);
    expect(container.querySelectorAll("mark")).toHaveLength(2);
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toBe("Acme <b>Ltd</b> acme");
  });
  it("handles regex characters in terms", () => {
    const { container } = render(<Highlight text="cost (USD) 5" terms={["(usd)"]} />);
    expect(container.querySelectorAll("mark")).toHaveLength(1);
  });
});
