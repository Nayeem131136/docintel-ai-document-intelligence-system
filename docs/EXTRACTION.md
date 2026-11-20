# AI extraction, validation and cross-verification (Phase 3)

Entry point: `documents/orchestrator.py` (`process_document`). It runs, in order:

```
text extraction / OCR  ->  segmentation  ->  AI extraction  ->  grounding check
                       ->  validation  ->  duplicate checks  ->  cross-verification
```

Each stage writes a `ProcessingEvent` (outcome and duration), so the history of every document is visible.

## 1. Segmentation (`extraction/segment.py`)

A PDF can hold many invoices. A new invoice starts only when a page shows an invoice number that
differs from the current one; pages without a number continue the current invoice. Pages with no invoice
data at all (a cover letter) are not saved as invoices; the document gets `NO_INVOICE_FOUND`.

Excel / CSV: if a sheet has a header row with an invoice-number column and a total column
(an "invoice register"), every row becomes one invoice with **no LLM call**. Other sheets are treated as
ordinary documents. Header names are matched against synonyms (`Invoice No`, `Inv #`, `Grand Total`...).

## 2. Extraction (`extraction/extractor.py`, `llm.py`, `prompts.py`)

- **LLM:** Groq chat-completions, JSON mode, temperature 0. The prompt (versioned `extract-v1`) tells the
  model to answer `null` rather than guess, never to calculate values, to treat the document as untrusted
  data, and gives an exact JSON schema.
- **Strict parsing:** the answer is validated field by field. Wrong types, unknown keys and malformed numbers
  or dates are ignored, never trusted.
- **Reliability:** retries with exponential backoff on HTTP 429 / 5xx and network errors (honours `Retry-After`).
  A bad key or model is not retried. After repeated failures the LLM is switched off for the rest of that
  document so a 1000-page file does not wait on every segment; remaining segments use the rules.
- **Rule-based fallback (`rules.py`):** used when no key/model is configured or the LLM fails. It only returns
  explicitly labelled values; the supplier is never guessed from the first line; a bare `$` is not turned
  into USD; an ambiguous date such as `03/04/2025` is left empty. Quality is lower than the LLM path and
  the result is flagged for review.
- **Cost / limits:** only invoice segments are sent (not every page), text is capped at
  `EXTRACTION_MAX_CHARS` (a `TEXT_TRUNCATED` warning is added when cut).

## 3. Never invent values: grounding (`extraction/grounding.py`)

Every value returned by the model is checked against the source text. A value that cannot be found there
is **dropped (set to NULL)** and recorded as `UNGROUNDED_VALUE`, with the dropped value kept in
`raw_output.dropped_ungrounded` for audit.

| Field | Grounded when |
|---|---|
| Invoice number, names, descriptions | found in the text, ignoring case, spacing and punctuation |
| Amounts, quantities | the number appears somewhere in the text (`1,150.00`, `1.150,00` and `1150` are equivalent) |
| Date | some date in the text can be read as that date (both day/month orders considered) |
| Currency | the code, or its symbol, appears in the text |

Missing values are stored as NULL, never `0` or an empty guess.

## 4. Validation (`extraction/validation.py`)

| Code | Severity | Meaning |
|---|---|---|
| `MISSING_FIELD` | error: invoice number, date, supplier, total. warning: currency, customer. info: subtotal, tax | a field was not found |
| `TOTAL_MISMATCH` | error (or warning when no tax was found) | subtotal + tax does not equal total (tolerance 0.02) |
| `SUBTOTAL_MISMATCH` | error | line items do not add up to the subtotal |
| `LINE_ITEM_MISMATCH` | error | quantity x unit price does not equal the line amount |
| `DUPLICATE_INVOICE` | error / warning | same supplier + invoice number already processed (PDF + Excel pairs are not duplicates) |
| `DUPLICATE_FILE` | warning | identical file (same SHA-256) uploaded before |
| `LOW_OCR_CONFIDENCE` | warning | mean OCR confidence below `LOW_OCR_CONFIDENCE` (default 0.80) |
| `NEGATIVE_AMOUNT`, `FUTURE_DATE`, `OLD_DATE`, `TAX_EXCEEDS_SUBTOTAL` | warning | implausible values |
| `UNGROUNDED_VALUE`, `AMBIGUOUS_DATE`, `INVALID_NUMBER`, `INVALID_DATE` | warning | extraction problems, see above |
| `EXTRACTION_FALLBACK` | warning (LLM failed) / info (no LLM configured) | rules were used instead of the LLM |
| `NOT_VERIFIABLE` | info | total could not be checked (no subtotal or lines) |
| `NO_INVOICE_FOUND` | error | nothing resembling an invoice in the document |
| `CROSS_CHECK_MISMATCH` | error | the same invoice differs between two documents |

A result with any error or warning gets `review_status = needs_review`; info never blocks. A document is
`completed` only when no result needs review and no page failed, otherwise `needs_review`.

## 5. Cross-verification (`extraction/crosscheck.py`)

When a document is processed, its invoices are compared with the same invoice number in other documents:

- **pdf_pdf:** PDF/scan against another PDF/scan.
- **pdf_excel:** PDF/scan against an Excel or CSV file.

Invoices are paired by invoice number and a matching supplier (company suffixes such as Ltd/Limited are
ignored) or an equal total, so two suppliers who both use `INV-001` are not confused. Supplier, customer,
date, currency, subtotal, tax, total and line-item count are compared. The outcome (`match`, `mismatch`,
`inconclusive`) and per-field differences are stored in `CrossVerification.details`. A mismatch adds
`CROSS_CHECK_MISMATCH` to both results and re-flags the earlier document too.
Spreadsheet-vs-spreadsheet is not compared.

## Limitations

- One invoice per page is assumed when splitting; two different invoices on one page are not separated.
- Rule-based extraction is a fallback, not a replacement for the LLM.
- Live Groq calls depend on your key, model and rate limits; they are covered by mocked tests, and real
  accuracy is measured in the Phase 7 evaluation.
- Reprocessing a document replaces its results (manual corrections on them are lost; the API in Phase 4
  will warn before doing that).
