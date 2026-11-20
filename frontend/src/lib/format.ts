import type { DocStatus, ReviewStatus, Severity } from "./types";

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${units[i]}`;
}

export function formatMoney(amount: string | number | null | undefined, currency?: string | null): string {
  if (amount === null || amount === undefined || amount === "") return "-";
  const number = Number(amount);
  if (!Number.isFinite(number)) return String(amount);
  const text = number.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${currency.toUpperCase()} ${text}` : text;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "-";
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min ${Math.round(seconds - minutes * 60)} s`;
}

export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "-" : `${Math.round(value * 100)}%`;
}

export const STATUS_META: Record<DocStatus, { label: string; tone: string }> = {
  queued: { label: "Queued", tone: "slate" },
  processing: { label: "Processing", tone: "blue" },
  completed: { label: "Completed", tone: "green" },
  needs_review: { label: "Needs review", tone: "amber" },
  failed: { label: "Failed", tone: "red" },
};

export const REVIEW_META: Record<ReviewStatus, { label: string; tone: string }> = {
  ok: { label: "OK", tone: "green" },
  needs_review: { label: "Needs review", tone: "amber" },
  reviewed: { label: "Reviewed", tone: "blue" },
};

export const SEVERITY_TONE: Record<Severity, string> = { error: "red", warning: "amber", info: "slate" };

export const isActive = (status: DocStatus) => status === "queued" || status === "processing";

export const ACCEPTED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"];
export const MAX_UPLOAD_MB = 50;

/** Client-side pre-check so obvious problems are reported instantly (the server validates again). */
export function checkFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return "Unsupported type (use PDF, JPG, PNG, TIFF, XLSX, XLS or CSV)";
  }
  if (file.size === 0) return "File is empty";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `Larger than ${MAX_UPLOAD_MB} MB`;
  return null;
}

export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const CODE_LABELS: Record<string, string> = {
  MISSING_FIELD: "Missing field",
  TOTAL_MISMATCH: "Total mismatch",
  SUBTOTAL_MISMATCH: "Subtotal mismatch",
  LINE_ITEM_MISMATCH: "Line item mismatch",
  DUPLICATE_INVOICE: "Duplicate invoice",
  DUPLICATE_FILE: "Duplicate file",
  LOW_OCR_CONFIDENCE: "Low OCR confidence",
  NEGATIVE_AMOUNT: "Negative amount",
  FUTURE_DATE: "Future date",
  OLD_DATE: "Very old date",
  TAX_EXCEEDS_SUBTOTAL: "Tax exceeds subtotal",
  NOT_VERIFIABLE: "Not verifiable",
  NO_INVOICE_FOUND: "No invoice found",
  CROSS_CHECK_MISMATCH: "Cross-check mismatch",
  UNGROUNDED_VALUE: "Value not in document",
};
export const issueLabel = (code: string) =>
  CODE_LABELS[code] ?? code.toLowerCase().replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
