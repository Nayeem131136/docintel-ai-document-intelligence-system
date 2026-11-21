# Evaluation Report

All numbers in this report were produced by `python manage.py run_evaluation` on the run described below. Nothing is estimated or typed in by hand; the same command regenerates the whole file.

## 1. Run details

| Item | Value |
|---|---|
| Date | 2026-11-21 16:52 UTC |
| Extraction mode | LLM (openai/gpt-oss-120b) |
| Embedding model (semantic search) | BAAI/bge-small-en-v1.5 |
| Dataset | 67 files, 116 invoices (seed 42, scale 1.0) |
| Machine | Linux-6.18.58.1-microsoft-standard-WSL2-x86_64-with-glibc2.41, 12 CPU threads, Python 3.12.16 |

**Dataset.** Synthetic invoices of fictional companies in three different layouts, rendered as digital PDFs, multi-invoice PDFs, long multi-page invoices, scanned PDFs, PNG/JPG images (rotated, blurred, noisy; the JPGs are smaller and unevenly lit to imitate phone photos), a multi-page TIFF, and XLSX / XLS / CSV registers with different header names. Money is written as `1,234.50`, `1.234,50` or with `€`/`£`; dates in four formats. Problems with a known expected outcome were injected: wrong printed totals, missing dates, identical files uploaded twice, the same invoice in two documents, and PDF-vs-Excel pairs with and without a differing total. The exact answer for every field is stored in `ground_truth.json` (exact by construction).

## 2. Field extraction

Across 116 invoices: **precision 99.3%**, **recall 98.2%**, **F1 98.7%**. 106 invoices (91.4%) had every field right. Invented values (the system filled in something wrong or where nothing exists): **0.71%** of the values it returned (7 wrong, 0 where the document has no value).

*Definitions.* Correct = equals the ground truth (names and numbers compared ignoring case and punctuation, amounts within 0.01, dates exactly). Precision = correct / values returned. Recall = correct / values that exist in the document. A value left empty counts against recall but not precision, because the system is designed to leave a field empty instead of guessing.

| Field | Correct | Wrong | Not found | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| Invoice number | 112 | 4 | 0 | 96.6% | 96.6% | 96.6% |
| Invoice date | 110 | 0 | 4 | 100.0% | 96.5% | 98.2% |
| Supplier | 114 | 2 | 0 | 98.3% | 98.3% | 98.3% |
| Customer | 115 | 1 | 0 | 99.1% | 99.1% | 99.1% |
| Currency | 114 | 0 | 2 | 100.0% | 98.3% | 99.1% |
| Subtotal | 115 | 0 | 1 | 100.0% | 99.1% | 99.6% |
| Discount | 66 | 0 | 1 | 100.0% | 98.5% | 99.2% |
| Tax | 114 | 0 | 2 | 100.0% | 98.3% | 99.1% |
| Total | 115 | 0 | 1 | 100.0% | 99.1% | 99.6% |

### By document type

| Type | Invoices | Fully correct | Precision | Recall |
|---|---|---|---|---|
| Digital PDF | 47 | 47 (100%) | 100.0% | 100.0% |
| Scanned PDF / PNG / TIFF | 13 | 7 (54%) | 97.0% | 89.0% |
| Photographed JPG | 4 | 0 (0%) | 87.5% | 82.4% |
| Excel / CSV register | 52 | 52 (100%) | 100.0% | 100.0% |

**Invoice detection:** found 116 of 116 invoices (recall 100.0%); 0 extra invoice(s) that do not exist (precision 100.0%). Line-item count matched exactly for 98.4% of the 64 invoices that have an item table.

**OCR:** mean engine confidence 98.0% over 16 scanned / photographed files (lowest 96.6%).

## 3. Validation and review flags

Detected **17 of 17** injected problems (100.0%).

| Problem | Injected | Detected |
|---|---|---|
| CROSS_CHECK_MISMATCH | 3 | 3 |
| DUPLICATE_FILE | 2 | 2 |
| DUPLICATE_INVOICE | 4 | 4 |
| MISSING_FIELD | 2 | 2 |
| TOTAL_MISMATCH | 6 | 6 |

False alarms: of 54 files with no injected problem, 1 raised an alarm although their extraction was fully correct (**1.9%**). A further 14 alarm(s) appeared on files whose extraction was itself wrong or incomplete; those are the validator correctly pointing at a real problem (for example a missing supplier), so they are not counted as false alarms.

Unexplained alarms by code: LINE_ITEM_MISMATCH x1.

## 4. Cross-verification (PDF vs PDF, PDF vs Excel)

12 invoice pairs: the comparison was found for 12, and the outcome (match / mismatch) was right for **12** (100.0%).

## 5. Search

Queries were generated from the ground truth: 20 by invoice number, 24 by product described in other words, 10 by supplier name. A result counts as relevant when it is a document that contains the invoice / supplier / product. Semantic and hybrid modes used the **BAAI/bge-small-en-v1.5** embedder.

| Query type | Mode | Queries | Hit@1 | Hit@5 | MRR |
|---|---|---|---|---|---|
| Invoice number | keyword | 20 | 100.0% | 100.0% | 1.000 |
| Invoice number | semantic | 20 | 40.0% | 75.0% | 0.541 |
| Invoice number | hybrid | 20 | 100.0% | 100.0% | 1.000 |
| Supplier name | keyword | 10 | 100.0% | 100.0% | 1.000 |
| Supplier name | semantic | 10 | 100.0% | 100.0% | 1.000 |
| Supplier name | hybrid | 10 | 100.0% | 100.0% | 1.000 |
| Product described in other words | keyword | 24 | 0.0% | 0.0% | 0.000 |
| Product described in other words | semantic | 24 | 87.5% | 100.0% | 0.938 |
| Product described in other words | hybrid | 24 | 87.5% | 100.0% | 0.938 |
| All queries | keyword | 54 | 55.6% | 55.6% | 0.556 |
| All queries | semantic | 54 | 72.2% | 90.7% | 0.802 |
| All queries | hybrid | 54 | 94.4% | 100.0% | 0.972 |

*Hit@k* = a relevant document is among the first k results. *MRR* = mean of 1 / rank of the first relevant result.

## 6. Performance

| File type | Files | Pages | Median per file | Slowest 5% | Total | Failed |
|---|---|---|---|---|---|---|
| csv_register | 4 | 4 | 722 ms | 1,088 ms | 2.9 s | 0 |
| digital_pdf | 43 | 51 | 8,769 ms | 26,681 ms | 417.1 s | 0 |
| jpg_image | 4 | 4 | 9,908 ms | 14,849 ms | 39.3 s | 0 |
| png_image | 4 | 4 | 8,280 ms | 9,557 ms | 33.0 s | 0 |
| scanned_pdf | 7 | 7 | 6,720 ms | 28,746 ms | 75.7 s | 0 |
| tiff_image | 1 | 2 | 24,333 ms | 24,333 ms | 24.3 s | 0 |
| xlsx_register | 4 | 4 | 748 ms | 1,102 ms | 3.0 s | 0 |

Processing outcome: completed 43, needs_review 24. Failure rate 0.0%.

## 7. Examples of mistakes

| File | Field | Problem | Expected | Got |
|---|---|---|---|---|
| 020_scanned.pdf | invoice_number | wrong | SI/1422 | Sl/1422 |
| 020_scanned.pdf | subtotal | missing | 32131.70 | None |
| 020_scanned.pdf | discount | missing | -3213.17 | None |
| 020_scanned.pdf | tax | missing | 3213.17 | None |
| 020_scanned.pdf | total | missing | 32131.70 | None |
| 024_scanned.pdf | invoice_date | missing | 2025-06-19 | None |
| 024_scanned.pdf | currency | missing | USD | None |
| 027_image.png | tax | missing | 0.00 | None |
| 030_photo.jpg | supplier_name | wrong | Meridian Software Corp | Meridlian Software Corp |
| 031_photo.jpg | invoice_number | wrong | A001659 | InvoiceA001659 |
| 031_photo.jpg | invoice_date | missing | 2025-04-11 | None |
| 032_photo.jpg | customer_name | wrong | Hooli Systems | Hool Systems |
| 033_photo.jpg | invoice_number | wrong | SI/1673 | Invoices/1673 |
| 033_photo.jpg | invoice_date | missing | 2025-01-02 | None |
| 034_multipage.tiff | invoice_date | missing | 2025-08-24 | None |
| 034_multipage.tiff | invoice_number | wrong | SI/1728 | Sl/1728 |
| 034_multipage.tiff | supplier_name | wrong | Riverbend Paper Mills | Rlverbend Paper Mills |
| 053_scanned.pdf | currency | missing | GBP | None |

## 8. Limitations of this evaluation

- The data is synthetic: three clean layouts and a fixed vocabulary. Real invoices are messier, so real-world accuracy can be lower, especially for scans. Treat these numbers as a reproducible benchmark of this system, not as a promise about every invoice.
- Scans and photos are simulated (rotation, blur, noise, lighting, lower resolution), not real camera images.
- One run on one machine; timings depend on the CPU, and LLM mode also depends on network latency and API limits.
- Semantic search quality depends on the embedding model; see the embedder named in section 1.
- Search queries were generated from the same ground truth; the product paraphrases were written by hand (12 products, 2 each).

## 9. Reproduce

```bash
cd backend
python manage.py generate_eval_dataset --out eval_data --seed 42
python manage.py run_evaluation --data eval_data --stress-pages 1000 --report ../docs/EVALUATION_REPORT.md
python manage.py run_evaluation --data eval_data --no-llm            # rule-based fallback only, for comparison
```
