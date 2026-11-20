# Database schema

PostgreSQL (with the pgvector extension, used for semantic search from Phase 5).
SQLite is used only for the optional no-Docker local mode.

```mermaid
erDiagram
    Document ||--o{ DocumentPage : "has text per page/sheet"
    Document ||--o{ ExtractionResult : "contains 1..n invoices"
    Document ||--o{ ProcessingEvent : "processing history"
    Document ||--o{ ValidationIssue : "flagged problems"
    ExtractionResult ||--o{ LineItem : "has"
    ExtractionResult ||--o{ ValidationIssue : "has"
    ExtractionResult ||--o{ CorrectionLog : "manual edits"
    Document ||--o{ CrossVerification : "document_a"
    Document ||--o{ CrossVerification : "document_b"

    Document {
        uuid id PK
        string original_filename
        string file_type
        string sha256
        string status
        int progress
        int page_count
        int attempts
        datetime uploaded_at
        bigint processing_time_ms
    }
    DocumentPage {
        int page_number
        string source "digital | ocr | spreadsheet"
        text text
        float ocr_confidence
    }
    ExtractionResult {
        string invoice_number
        date invoice_date
        string supplier_name
        string customer_name
        string currency
        decimal subtotal
        decimal tax
        decimal total
        json confidence
        string review_status
        string dedupe_key
    }
    LineItem {
        text description
        decimal quantity
        decimal unit_price
        decimal amount
    }
    ValidationIssue {
        string code
        string severity
        string field
        text message
        bool resolved
    }
    CorrectionLog {
        string field
        text old_value
        text new_value
    }
    ProcessingEvent {
        string stage
        string outcome
        bigint duration_ms
    }
    CrossVerification {
        string check_type "pdf_pdf | pdf_excel"
        string outcome
        json details
    }
```

## Design decisions

- **One document, many invoices.** A ~1000-page PDF can hold many invoices, so
  `ExtractionResult` is a child of `Document` (with `page_start` / `page_end`).
- **Missing values are NULL.** Extracted fields are nullable; the system never
  stores a guessed value or a default `0`.
- **Duplicate detection.** `Document.sha256` catches identical re-uploads;
  `ExtractionResult.dedupe_key` (normalised supplier + invoice number) catches the
  same invoice arriving as a different file.
- **Audit trail.** `ProcessingEvent` records every stage with duration and outcome;
  `CorrectionLog` records every manual change (old value -> new value).
- **Cross-verification** (pdf-pdf, pdf-excel) is stored in `CrossVerification` with
  per-field differences in `details`.
- **Indexes** on status, supplier, invoice number/date and dedupe key keep filtering
  fast as volume grows.
- A vector-embedding table for semantic search is added in Phase 5.
