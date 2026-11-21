import type {
  Doc, DocResults, DocStatusResponse, Invoice, InvoiceSummary, InvoiceWrite, Issue, Page, PageText, SearchResponse,
  Stats, UploadResponse,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";
const TOKEN_KEY = "docintel.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session just will not persist */
  }
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public body?: unknown) {
    super(message);
  }
  /** Field-level messages from a DRF validation error, e.g. {total: "A valid number is required."} */
  get fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    if (this.body && typeof this.body === "object") {
      for (const [key, value] of Object.entries(this.body as Record<string, unknown>)) {
        out[key] = flatten(value);
      }
    }
    return out;
  }
}

function flatten(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(flatten).filter(Boolean).join(" ");
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => (/^\d+$/.test(k) ? flatten(v) : `${k}: ${flatten(v)}`))
      .join(" ");
  }
  return value === null || value === undefined ? "" : String(value);
}

export function messageFromBody(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    const parts = Object.entries(record).map(([k, v]) => (k === "non_field_errors" ? flatten(v) : `${k}: ${flatten(v)}`));
    if (parts.length) return parts.join(" ");
  }
  if (status === 413) return "The file is too large for the server.";
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  if (status >= 500) return "The server had a problem. Please try again.";
  return `Request failed (${status}).`;
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

export async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Token ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers, body });
  } catch {
    throw new ApiError("Cannot reach the server. Check that the backend is running.", 0);
  }
  if (response.status === 204) return undefined as T;
  let data: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    if (response.status === 401 && token) onUnauthorized?.();
    throw new ApiError(messageFromBody(data, response.status), response.status, data);
  }
  return data as T;
}

const qs = (params: Record<string, string | number | boolean | undefined | null>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "" && value !== false) search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
};

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; username: string; is_staff: boolean }>("/auth/token/", { method: "POST", json: { username, password } }),
  me: () => request<{ username: string; is_staff: boolean }>("/auth/me/"),
  stats: () => request<Stats>("/stats/"),

  documents: (params: Record<string, string | number | undefined>) => request<Page<Doc>>(`/documents/${qs(params)}`),
  document: (id: string) => request<Doc>(`/documents/${id}/`),
  documentStatus: (id: string) => request<DocStatusResponse>(`/documents/${id}/status/`),
  documentResults: (id: string) => request<DocResults>(`/documents/${id}/results/`),
  documentPages: (id: string, page: number) => request<Page<PageText>>(`/documents/${id}/pages/${qs({ page, page_size: 20 })}`),
  deleteDocument: (id: string) => request<void>(`/documents/${id}/`, { method: "DELETE" }),
  reprocess: (id: string, force = false) => request<Doc>(`/documents/${id}/reprocess/`, { method: "POST", json: { force } }),
  reprocessFailed: () => request<{ queued: number }>("/documents/reprocess-failed/", { method: "POST" }),
  createInvoice: (docId: string, data: InvoiceWrite) =>
    request<Invoice>(`/documents/${docId}/results/`, { method: "POST", json: data }),
  async fileBlob(id: string): Promise<Blob> {
    const token = getToken();
    const response = await fetch(`${BASE}/documents/${id}/file/`, { headers: token ? { Authorization: `Token ${token}` } : {} });
    if (!response.ok) throw new ApiError("The original file could not be loaded.", response.status);
    return response.blob();
  },

  invoices: (params: Record<string, string | number | boolean | undefined>) =>
    request<Page<InvoiceSummary>>(`/results/${qs(params)}`),
  updateInvoice: (id: number, data: InvoiceWrite) => request<Invoice>(`/results/${id}/`, { method: "PATCH", json: data }),
  approveInvoice: (id: number) => request<Invoice>(`/results/${id}/approve/`, { method: "POST" }),
  resolveIssue: (id: number) => request<Issue>(`/issues/${id}/resolve/`, { method: "POST" }),

  search: (params: Record<string, string | number | undefined>) => request<SearchResponse>(`/search/${qs(params)}`),
};

/** Upload one file with real progress events (fetch cannot report upload progress). */
/** Public liveness probe used by the header status pill. Never throws: false means "cannot reach the API". */
export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${BASE}/health/`, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

export function uploadFile(file: File, onProgress: (fraction: number) => void): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/documents/`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Token ${token}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onerror = () => reject(new ApiError("Cannot reach the server. Check that the backend is running.", 0));
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        data = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data as UploadResponse);
      if (xhr.status === 401) onUnauthorized?.();
      const rejected = (data as UploadResponse | null)?.rejected?.[0];
      reject(new ApiError(rejected?.error ?? messageFromBody(data, xhr.status), xhr.status, data));
    };
    const form = new FormData();
    form.append("files", file);
    xhr.send(form);
  });
}
