import { vi } from "vitest";
import { ApiError, api, getToken, messageFromBody, setToken, setUnauthorizedHandler } from "../lib/api";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}
afterEach(() => { vi.unstubAllGlobals(); setUnauthorizedHandler(null); });

describe("api client", () => {
  it("sends the token and parses JSON", async () => {
    setToken("abc");
    const fetchMock = mockFetch(200, { username: "alice", is_staff: false });
    expect(await api.me()).toEqual({ username: "alice", is_staff: false });
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Token abc");
  });
  it("stores the token safely", () => {
    setToken("t");
    expect(getToken()).toBe("t");
    setToken(null);
    expect(getToken()).toBeNull();
  });
  it("turns validation errors into readable messages and field errors", async () => {
    mockFetch(400, { total: ["A valid number is required."], currency: ["Use a 3-letter currency code."] });
    const error = await api.updateInvoice(1, { total: "x" }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(400);
    expect(error.fieldErrors.total).toBe("A valid number is required.");
    expect(error.message).toContain("total");
  });
  it("calls the unauthorized handler on 401 when a token was sent", async () => {
    setToken("expired");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(401, { detail: "Invalid token." });
    await expect(api.stats()).rejects.toThrow("Invalid token.");
    expect(handler).toHaveBeenCalledOnce();
  });
  it("does not treat a failed login as an expired session", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(400, { non_field_errors: ["Unable to log in with provided credentials."] });
    await expect(api.login("a", "b")).rejects.toThrow(/Unable to log in/);
    expect(handler).not.toHaveBeenCalled();
  });
  it("reports an unreachable server clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.stats()).rejects.toThrow(/Cannot reach the server/);
  });
  it("handles 204 and non-JSON error pages", async () => {
    mockFetch(204, undefined);
    await expect(api.deleteDocument("x")).resolves.toBeUndefined();
    expect(messageFromBody(null, 413)).toMatch(/too large/);
    expect(messageFromBody(null, 500)).toMatch(/server/);
    expect(messageFromBody(null, 429)).toMatch(/Too many/);
  });
  it("builds query strings without empty values", async () => {
    const fetchMock = mockFetch(200, { count: 0, results: [] });
    await api.invoices({ q: "acme", currency: "", has_issues: false, page: 2 });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/results/?q=acme&page=2");
  });
});
