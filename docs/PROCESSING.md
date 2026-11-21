# Document processing

Entry points: `documents/processing/pipeline.py`
(`create_document_from_path`, `extract_document_text`) and the CLI
`python manage.py process_files`.

## Flow

```
file -> detect type + safety checks -> extractor (streams pages) -> DocumentPage rows
                                                         \-> ProcessingEvent history, progress, timings
```

## Validation before parsing (`detect.py`)

- Type is decided from the **file content** (magic bytes), not only the extension.
- Rejected up front: unsupported extension, empty file, content that does not match the
  extension (e.g. a PDF renamed to .png), binary data named .csv, files over `MAX_UPLOAD_SIZE_MB`.
- Tolerated: Excel files saved with the wrong extension (.xls holding XLSX data, and vice versa).

## Per file type

| Type | Library | Behaviour |
|---|---|---|
| Digital PDF | PyMuPDF | Reads the text layer page by page, in reading order. No OCR needed, so it is fast (1000 pages in well under a second in tests). |
| Scanned PDF | PyMuPDF + RapidOCR | A page with almost no text (or one big image with a tiny text stamp) is rendered at `OCR_DPI` (default 200) and OCR'd. Digital and scanned pages can be mixed in one file. Blank pages are detected and skipped. |
| JPG / PNG / TIFF | Pillow + RapidOCR | OCR per image. Multi-page TIFF gives one page per frame. EXIF rotation is applied. |
| XLSX | openpyxl (read-only) | One page per sheet. Text is one line per row (cells joined by ` | `); raw rows are also kept as JSON in `DocumentPage.table` for later PDF-vs-Excel cross-checks. |
| XLS | xlrd | Same output as XLSX. |
| CSV | csv module | Encoding detection (UTF-8, UTF-8 BOM, UTF-16, Windows-1252), delimiter detection (`, ; tab |`), quoted multi-line cells. |

## OCR quality handling (`ocr.py`)

1. Light preprocessing: grayscale, auto-contrast, upscale small images, downscale huge ones.
2. If the result is weak (low mean confidence or very little text), retry with a stronger
   variant (denoise + sharpen) and with 90 / 270 degree rotations; keep the best attempt.
3. Recognised text boxes are regrouped into lines so a table row stays on one line.
4. Mean OCR confidence is stored per page (`DocumentPage.ocr_confidence`) so low-quality
   pages can be flagged for manual review in later phases.

## Failure handling

| Situation | Result |
|---|---|
| Corrupted / truncated / invalid file | Document `failed`, readable `error_message` (no server paths or internals) |
| Password-protected PDF | Document `failed`: "password-protected" |
| One bad page or sheet in a larger file | That page is flagged (`has_error`); the rest is processed; document becomes `needs_review` |
| Every page failed | Document `failed` |
| Huge PDF (over `MAX_PDF_PAGES`) | Rejected with a clear message |
| XLSX zip bomb (decompressed size over `MAX_UNCOMPRESSED_MB`) | Rejected before parsing |
| Image decompression bomb | Rejected (`Image.MAX_IMAGE_PIXELS`) |
| Sheet over `MAX_SPREADSHEET_ROWS` | Truncated with a warning on that page |
| Unexpected exception | Caught, logged, document `failed`; the worker never crashes |

Full details of each failure go to the server log; users only see a short message.

## Performance and scalability notes

- Pages are **streamed** and written to the database in batches of 20, so memory stays flat
  for ~1000-page files and `progress` / `pages_processed` update while the job runs.
- Digital PDFs and spreadsheets are CPU-light. **Scanned pages are the slow path**
  (roughly 1-3 seconds per page on CPU), so each document runs as a background
  Celery job and workers can be scaled out with `docker compose up --scale worker=N`.
- The OCR model is loaded once per process and reused.
- Measured throughput is reported in the evaluation report (not estimated here).

## Known limitations

- Handwriting is not supported (RapidOCR targets printed text).
- Very low-resolution or heavily skewed scans lower OCR accuracy; such pages show low confidence.
- Formula cells in XLSX return the last value cached by Excel; a file never opened in Excel may show empty cells.
- Hidden spreadsheet sheets are processed like visible ones.
