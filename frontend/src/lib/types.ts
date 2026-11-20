
export type DocStatus = "queued" | "processing" | "completed" | "needs_review" | "failed";
export type ReviewStatus = "ok" | "needs_review" | "reviewed";
export type Severity = "error" | "warning" | "info";

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Doc {
  id: string;
  original_filename: string;
  file_type: string;
  size_bytes: number;
  status: DocStatus;
  progress: number;
  page_count: number;
  pages_processed: number;
  error_message: string;
  attempts: number;
  uploaded_at: string;
  processed_at: string | null;
  processing_time_ms: number | null;
  invoice_count: number;
  review_count: number;
}

export interface ProcessingEvent {
  stage: string;
  outcome: string;
  message: string;
  duration_ms: number | null;
  created_at: string;
}

export interface DocStatusResponse extends Doc {
  events: ProcessingEvent[];
}

export interface Issue {
  id: number;
  code: string;
  severity: Severity;
  field: string;
  message: string;
  expected: string;
  found: string;
  resolved: boolean;
  created_at: string;
}

export interface LineItem {
  position?: number;
  description: string | null;
  quantity: string | null;
  unit_price: string | null;
  amount: string | null;
}

export interface Correction {
  id: number;
  field: string;
  old_value: string;
  new_value: string;
  note: string;
  corrected_at: string;
}

export interface Invoice {
  id: number;
  document: string;
  filename: string;
  page_start: number | null;
  page_end: number | null;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  customer_name: string | null;
  currency: string | null;
  subtotal: string | null;
  discount: string | null;
  tax: string | null;
  total: string | null;
  line_items: LineItem[];
  confidence: Record<string, number>;
  method: "llm" | "rules" | "manual";
  model_name: string;
  review_status: ReviewStatus;
  issues: Issue[];
  corrections: Correction[];
  created_at: string;
  updated_at: string;
}

export interface InvoiceSummary {
  id: number;
  document: string;
  filename: string;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  customer_name: string | null;
  currency: string | null;
  subtotal: string | null;
  discount: string | null;
  tax: string | null;
  total: string | null;
  review_status: ReviewStatus;
  method: string;
  open_issues: number;
  created_at: string;
}

export interface CrossCheck {
  id: number;
  check_type: "pdf_pdf" | "pdf_excel";
  document_a: string;
  document_b: string;
  outcome: "match" | "mismatch" | "inconclusive";
  details: {
    invoices: {
      invoice_number: string | null;
      outcome: string;
      fields: Record<string, { a: string | null; b: string | null; match: boolean }>;
    }[];
  };
  created_at: string;
}

export interface DocResults {
  document: Doc;
  results: Invoice[];
  document_issues: Issue[];
  cross_checks: CrossCheck[];
}

export interface PageText {
  page_number: number;
  sheet_name: string;
  source: string;
  ocr_confidence: number | null;
  has_error: boolean;
  error_message: string;
  text: string;
}

export interface Stats {
  documents: { total: number; by_status: Partial<Record<DocStatus, number>> };
  processing: { success_rate: number | null; failure_rate: number | null; avg_time_ms: number | null };
  invoices: { total: number; needs_review: number };
  open_issues: number;
}

export interface SearchHit {
  kind: "invoice" | "page";
  score: number;
  keyword_score: number | null;
  semantic_score: number | null;
  document: { id: string; filename: string; file_type: string; status: DocStatus };
  page_number: number | null;
  snippet: string;
  invoice?: {
    id: number;
    invoice_number: string | null;
    supplier_name: string | null;
    customer_name: string | null;
    invoice_date: string | null;
    subtotal?: string | null;
    discount?: string | null;
    tax?: string | null;
    total: string | null;
    currency: string | null;
    review_status: ReviewStatus;
  };
}

export interface SearchResponse {
  query: string;
  mode: string;
  terms: string[];
  semantic_model: string | null;
  count: number;
  results: SearchHit[];
}

export interface UploadResponse {
  documents: Doc[];
  rejected: { filename: string; error: string }[];
}

export interface InvoiceWrite {
  invoice_number?: string | null;
  invoice_date?: string | null;
  supplier_name?: string | null;
  customer_name?: string | null;
  currency?: string | null;
  subtotal?: string | null;
  discount?: string | null;
  tax?: string | null;
  total?: string | null;
  line_items?: LineItem[];
  note?: string;
}
