# Evaluation Report

All numbers in this report were produced by `python manage.py run_evaluation` on the run described below. Nothing is estimated or typed in by hand; the same command regenerates the whole file.

## 1. Run details

| Item | Value |
|---|---|
| Date | 2026-11-20 21:48 UTC |
| Extraction mode | rule-based (no LLM) |
| Embedding model (semantic search) | hashing-384 |
| Dataset | 68 files, 124 invoices (seed 42, scale 1.0) |
| Machine | Linux-6.18.44-fc-v726-x86_64-with-glibc2.39, 2 CPU threads, Python 3.13.18 |

> This run used the **rule-based fallback only** (what the app does when no LLM is configured). To measure the LLM path, put `GROQ_API_KEY` and `GROQ_MODEL` in `.env` and run the command in section 9 without `--no-llm`.

**Dataset.** Synthetic invoices of fictional companies in three different layouts, rendered as digital PDFs, multi-invoice PDFs, long multi-page invoices, scanned PDFs, PNG/JPG images (rotated, blurred, noisy; the JPGs are smaller and unevenly lit to imitate phone photos), a multi-page TIFF, and XLSX / XLS / CSV registers with different header names. Money is written as `1,234.50`, `1.234,50` or with `€`/`£`; dates in four formats. Problems with a known expected outcome were injected: wrong printed totals, missing dates, identical files uploaded twice, the same invoice in two documents, and PDF-vs-Excel pairs with and without a differing total. The exact answer for every field is stored in `ground_truth.json` (exact by construction).

## 2. Field extraction

Across 124 invoices: **precision 99.7%**, **recall 97.4%**, **F1 98.5%**. 101 invoices (81.5%) had every field right. Invented values (the system filled in something wrong or where nothing exists): **0.29%** of the values it returned (3 wrong, 0 where the document has no value).

*Definitions.* Correct = equals the ground truth (names and numbers compared ignoring case and punctuation, amounts within 0.01, dates exactly). Precision = correct / values returned. Recall = correct / values that exist in the document. A value left empty counts against recall but not precision, because the system is designed to leave a field empty instead of guessing.

| Field | Correct | Wrong | Not found | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| Invoice number | 124 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| Invoice date | 122 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| Supplier | 103 | 1 | 20 | 99.0% | 83.1% | 90.4% |
| Customer | 122 | 2 | 0 | 98.4% | 98.4% | 98.4% |
| Currency | 121 | 0 | 3 | 100.0% | 97.6% | 98.8% |
| Subtotal | 123 | 0 | 1 | 100.0% | 99.2% | 99.6% |
| Discount | 71 | 0 | 1 | 100.0% | 98.6% | 99.3% |
| Tax | 124 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| Total | 124 | 0 | 0 | 100.0% | 100.0% | 100.0% |

### By document type

| Type | Invoices | Fully correct | Precision | Recall |
|---|---|---|---|---|
| Digital PDF | 47 | 33 (70%) | 100.0% | 96.5% |
| Scanned PDF / PNG / TIFF | 13 | 8 (62%) | 100.0% | 92.7% |
| Photographed JPG | 4 | 0 (0%) | 90.3% | 82.4% |
| Excel / CSV register | 60 | 60 (100%) | 100.0% | 100.0% |

**Invoice detection:** found 124 of 124 invoices (recall 100.0%); 0 extra invoice(s) that do not exist (precision 100.0%). Line-item count matched exactly for 78.1% of the 64 invoices that have an item table.

**OCR:** mean engine confidence 82.2% over 16 scanned / photographed files (lowest 80.9%).

## 3. Validation and review flags

Detected **13 of 17** injected problems (76.5%).

| Problem | Injected | Detected |
|---|---|---|
| CROSS_CHECK_MISMATCH | 3 | 3 |
| DUPLICATE_FILE | 2 | 2 |
| DUPLICATE_INVOICE | 4 | 0 |
| MISSING_FIELD | 2 | 2 |
| TOTAL_MISMATCH | 6 | 6 |

False alarms: of 55 files with no injected problem, 1 raised an alarm although their extraction was fully correct (**1.8%**). A further 31 alarm(s) appeared on files whose extraction was itself wrong or incomplete; those are the validator correctly pointing at a real problem (for example a missing supplier), so they are not counted as false alarms.

Unexplained alarms by code: CROSS_CHECK_MISMATCH x1.

Injected problems that were **not** detected:

| File | Expected flag |
|---|---|
| 050_pair_b.pdf | DUPLICATE_INVOICE |
| 052_pair_b.pdf | DUPLICATE_INVOICE |
| 054_scanned.pdf | DUPLICATE_INVOICE |
| 056_pair_b.pdf | DUPLICATE_INVOICE |

## 4. Cross-verification (PDF vs PDF, PDF vs Excel)

12 invoice pairs: the comparison was found for 12, and the outcome (match / mismatch) was right for **11** (91.7%).

| Type | Invoice | Expected | Got |
|---|---|---|---|
| pdf_pdf | INV-2025-02632 | match | mismatch |

## 5. Search

Queries were generated from the ground truth: 20 by invoice number, 24 by product described in other words, 10 by supplier name. A result counts as relevant when it is a document that contains the invoice / supplier / product. Semantic and hybrid modes used the **hashing-384** embedder. This is the built-in offline fallback, which matches words and spellings but not meaning, so the semantic numbers below understate what the real model achieves; re-run on a machine that can download the model.

| Query type | Mode | Queries | Hit@1 | Hit@5 | MRR |
|---|---|---|---|---|---|
| Invoice number | keyword | 20 | 100.0% | 100.0% | 1.000 |
| Invoice number | semantic | 20 | 30.0% | 35.0% | 0.317 |
| Invoice number | hybrid | 20 | 100.0% | 100.0% | 1.000 |
| Supplier name | keyword | 10 | 100.0% | 100.0% | 1.000 |
| Supplier name | semantic | 10 | 90.0% | 90.0% | 0.900 |
| Supplier name | hybrid | 10 | 100.0% | 100.0% | 1.000 |
| Product described in other words | keyword | 24 | 0.0% | 0.0% | 0.000 |
| Product described in other words | semantic | 24 | 29.2% | 29.2% | 0.292 |
| Product described in other words | hybrid | 24 | 29.2% | 29.2% | 0.292 |
| All queries | keyword | 54 | 55.6% | 55.6% | 0.556 |
| All queries | semantic | 54 | 40.7% | 42.6% | 0.414 |
| All queries | hybrid | 54 | 68.5% | 68.5% | 0.685 |

*Hit@k* = a relevant document is among the first k results. *MRR* = mean of 1 / rank of the first relevant result.

## 6. Performance

| File type | Files | Pages | Median per file | Slowest 5% | Total | Failed |
|---|---|---|---|---|---|---|
| csv_register | 4 | 4 | 48 ms | 61 ms | 0.2 s | 0 |
| digital_pdf | 43 | 51 | 24 ms | 45 ms | 1.2 s | 0 |
| jpg_image | 4 | 4 | 1,072 ms | 1,186 ms | 4.1 s | 0 |
| png_image | 4 | 4 | 1,686 ms | 1,787 ms | 6.7 s | 0 |
| scanned_pdf | 7 | 7 | 2,388 ms | 3,107 ms | 17.0 s | 0 |
| tiff_image | 1 | 2 | 3,282 ms | 3,282 ms | 3.3 s | 0 |
| xls_register | 1 | 1 | 65 ms | 65 ms | 0.1 s | 0 |
| xlsx_register | 4 | 4 | 53 ms | 59 ms | 0.2 s | 0 |

Processing outcome: completed 31, needs_review 37. Failure rate 0.0%.

### Large document

| Item | Value |
|---|---|
| Document | 1000 pages, 10.6 MB, 200 invoices |
| Extraction | rule-based (LLM off: a 1000-page file would otherwise make one API call per invoice) |
| Result | completed, 200 of 200 invoices found |
| Total time | 12.0 s (83.0 pages/s) |
| Peak memory of the whole run | 190.1 MB |

## 7. Examples of mistakes

| File | Field | Problem | Expected | Got |
|---|---|---|---|---|
| 002_digital.pdf | supplier_name | missing | Delta Wave Communications | None |
| 005_digital.pdf | supplier_name | missing | Omega Printing Co | None |
| 008_digital.pdf | supplier_name | missing | Harbor Point Electronics | None |
| 011_digital.pdf | supplier_name | missing | Omega Printing Co | None |
| 014_digital.pdf | supplier_name | missing | Northwind Hardware | None |
| 016_multi_invoice.pdf | supplier_name | missing | Ironclad Industrial Supply | None |
| 017_multi_invoice.pdf | supplier_name | missing | Omega Printing Co | None |
| 023_scanned.pdf | supplier_name | missing | Acme Trading Ltd | None |
| 024_scanned.pdf | supplier_name | missing | Redwood Furniture Co | None |
| 024_scanned.pdf | currency | missing | USD | None |
| 028_image.png | supplier_name | missing | Omega Printing Co | None |
| 028_image.png | currency | missing | USD | None |
| 030_photo.jpg | supplier_name | wrong | Meridian Software Corp | Merldian Software Corp |
| 030_photo.jpg | customer_name | wrong | Wonka Confectionery | Wonka Confectlonery |
| 031_photo.jpg | supplier_name | missing | Pioneer Networks GmbH | None |
| 032_photo.jpg | customer_name | wrong | Hooli Systems | Hoolil Systems |
| 032_photo.jpg | subtotal | missing | 12857.71 | None |
| 033_photo.jpg | supplier_name | missing | Lotus Stationery House | None |
| 034_multipage.tiff | discount | missing | -1135.35 | None |
| 040_wrong_total.pdf | supplier_name | missing | Northwind Hardware | None |

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
