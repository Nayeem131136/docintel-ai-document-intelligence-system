# Database schema

PostgreSQL. SQLite is used only for the optional no-Docker local mode.

![Entity relationship diagram](images/er.png)

Mermaid source (renders on GitHub):

```mermaid
erDiagram
    User ||--o{ Document : owns
    Document ||--o{ DocumentPage : "text per page or sheet"
    Document ||--o{ ExtractionResult : "1 to n invoices"
    Document ||--o{ ProcessingEvent : "processing history"
    Document ||--o{ ValidationIssue : "document-level flags"
    Document ||--o{ SearchChunk : "search index"
    Document ||--o{ CrossVerification : "document_a / document_b"
    ExtractionResult ||--o{ LineItem : has
    ExtractionResult ||--o{ ValidationIssue : "invoice-level flags"
    ExtractionResult ||--o{ CorrectionLog : "manual edits"
    ExtractionResult ||--o{ SearchChunk : "invoice summary"

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
        string source "digital, ocr, spreadsheet"
        text text
        float ocr_confidence
        json table
    }
    ExtractionResult {
        string invoice_number
        date invoice_date
        string supplier_name
        string customer_name
        string currency
        decimal subtotal
        decimal discount "negative, only if printed"
        decimal tax
        decimal total
        json confidence
        string method "llm, rules, manual"
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
        text note
    }
    ProcessingEvent {
        string stage
        string outcome
        bigint duration_ms
    }
    CrossVerification {
        string check_type "pdf_pdf, pdf_excel"
        string outcome
        json details
    }
    SearchChunk {
        string kind "invoice, page"
        int page_number
        text text
        binary embedding
        string embedding_model
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
- **Search index.** `SearchChunk` stores searchable text (an invoice summary or a slice of a page) and its
  embedding as raw float32 bytes plus the name of the model that produced it, so keyword and semantic search work
  on SQLite and PostgreSQL alike and vectors from different models are never compared. For a very large
  collection a pgvector column with an HNSW index is the next step.
- **Ownership.** `Document.owner` links each document to a user; every API query is filtered by it.
