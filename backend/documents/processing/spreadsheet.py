"""Spreadsheet parsing: XLSX (openpyxl), legacy XLS (xlrd) and CSV (csv module).

Each sheet becomes one "page". For every sheet we keep both:
  * ``text``  - one line per row, cells joined with " | " (what the LLM reads), and
  * ``table`` - the raw rows as JSON (what PDF-vs-Excel cross-verification compares).
"""
import csv
import io
import logging
import math
import zipfile
from datetime import date, datetime, time
from decimal import Decimal

from . import config
from .base import Extraction, PageResult, clean_text
from .errors import CorruptedFileError, FileTooLargeError, PasswordProtectedError

logger = logging.getLogger(__name__)


def _normalise(value):
    """Convert a cell value to something JSON-serialisable and PostgreSQL-safe."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0, 0) else value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return int(value) if value.is_integer() and abs(value) < 1e15 else value
    if isinstance(value, int):
        return value
    text = clean_text(str(value)).strip()
    return text or None


def _finish_sheet(number: int, name: str, rows: list[list], truncated: bool) -> PageResult:
    lines = []
    for row in rows:
        cells = ["" if cell is None else str(cell) for cell in row]
        lines.append(" | ".join(cells))
    warning = ""
    if truncated:
        warning = f"Sheet truncated to the first {len(rows)} non-empty rows."
    return PageResult(
        page_number=number,
        text=clean_text("\n".join(lines)),
        source="spreadsheet",
        sheet_name=clean_text(name),
        table={"rows": rows, "truncated": truncated},
        warning=warning,
    )


def _clean_row(values) -> list | None:
    row = [_normalise(v) for v in values]
    while row and row[-1] is None:
        row.pop()
    return row or None   # None => completely empty row (skipped)


# --------------------------------------------------------------------------- XLSX
def extract_xlsx(path: str) -> Extraction:
    from openpyxl import load_workbook

    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise CorruptedFileError("The XLSX file is corrupted (bad zip entry).")
            uncompressed = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise CorruptedFileError("The XLSX file is corrupted (not a valid zip container).") from exc
    if uncompressed > config.max_uncompressed_bytes():
        raise FileTooLargeError(
            f"The XLSX expands to {uncompressed // 1_048_576} MB, above the "
            f"{config.max_uncompressed_bytes() // 1_048_576} MB safety limit."
        )

    # Open via a file object: openpyxl refuses to open a path whose extension is not
    # .xlsx, but the content (checked above) is what matters.
    handle = open(path, "rb")
    try:
        workbook = load_workbook(handle, read_only=True, data_only=True)
        names = list(workbook.sheetnames)
    except Exception as exc:  # noqa: BLE001 - openpyxl raises assorted XML/zip errors on bad files
        handle.close()
        raise CorruptedFileError(f"The XLSX file could not be opened ({type(exc).__name__}).") from exc
    if not names:
        workbook.close()
        handle.close()
        raise CorruptedFileError("The workbook has no sheets.")

    limit = config.max_spreadsheet_rows()

    def pages():
        try:
            for index, name in enumerate(names):
                number = index + 1
                try:
                    rows, truncated = [], False
                    for values in workbook[name].iter_rows(values_only=True):
                        row = _clean_row(values)
                        if row is None:
                            continue
                        if len(rows) >= limit:
                            truncated = True
                            break
                        rows.append(row)
                    yield _finish_sheet(number, name, rows, truncated)
                except Exception as exc:  # noqa: BLE001 - isolate a bad sheet
                    logger.warning("XLSX sheet %r failed: %s", name, exc)
                    yield PageResult(number, source="spreadsheet", sheet_name=clean_text(name),
                                     error=f"Sheet could not be read ({type(exc).__name__}).")
        finally:
            workbook.close()
            handle.close()

    return Extraction(total=len(names), pages=pages())


# --------------------------------------------------------------------------- XLS
def extract_xls(path: str) -> Extraction:
    import xlrd

    try:
        workbook = xlrd.open_workbook(path, on_demand=True)
    except xlrd.biffh.XLRDError as exc:
        message = str(exc)
        if "crypt" in message.lower() or "password" in message.lower():
            raise PasswordProtectedError("The Excel file is password-protected.") from exc
        raise CorruptedFileError(f"The XLS file could not be opened (corrupted or unsupported).") from exc
    except Exception as exc:  # noqa: BLE001
        raise CorruptedFileError(f"The XLS file could not be opened ({type(exc).__name__}).") from exc

    total = workbook.nsheets
    if total == 0:
        workbook.release_resources()
        raise CorruptedFileError("The workbook has no sheets.")
    limit = config.max_spreadsheet_rows()

    def cell_value(cell):
        if cell.ctype == xlrd.XL_CELL_DATE:
            try:
                return xlrd.xldate_as_datetime(cell.value, workbook.datemode)
            except Exception:  # noqa: BLE001
                return cell.value
        if cell.ctype == xlrd.XL_CELL_BOOLEAN:
            return bool(cell.value)
        if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
            return None
        return cell.value

    def pages():
        try:
            for index in range(total):
                number = index + 1
                name = f"Sheet{number}"
                try:
                    sheet = workbook.sheet_by_index(index)
                    name = sheet.name
                    rows, truncated = [], False
                    for row_index in range(sheet.nrows):
                        row = _clean_row(cell_value(c) for c in sheet.row(row_index))
                        if row is None:
                            continue
                        if len(rows) >= limit:
                            truncated = True
                            break
                        rows.append(row)
                    workbook.unload_sheet(index)
                    yield _finish_sheet(number, name, rows, truncated)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("XLS sheet %r failed: %s", name, exc)
                    yield PageResult(number, source="spreadsheet", sheet_name=clean_text(name),
                                     error=f"Sheet could not be read ({type(exc).__name__}).")
        finally:
            workbook.release_resources()

    return Extraction(total=total, pages=pages())


# --------------------------------------------------------------------------- CSV
def _decode(raw: bytes) -> str:
    """Decode bytes trying the encodings that real-world exports use."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")   # never fails


def _delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in (",", ";", "\t", "|")}
        best = max(counts, key=counts.get)
        return best if counts[best] else ","


def extract_csv(path: str) -> Extraction:
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise CorruptedFileError(f"The CSV file could not be read ({type(exc).__name__}).") from exc

    text = _decode(raw)
    if not text.strip():
        raise CorruptedFileError("The CSV file contains no data.")

    csv.field_size_limit(10_000_000)
    delimiter = _delimiter(text[:8192])
    limit = config.max_spreadsheet_rows()
    rows, truncated = [], False
    try:
        # StringIO(newline="") keeps line breaks inside quoted cells intact.
        for values in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter):
            row = _clean_row(values)
            if row is None:
                continue
            if len(rows) >= limit:
                truncated = True
                break
            rows.append(row)
    except csv.Error as exc:
        raise CorruptedFileError(f"The CSV file is malformed ({type(exc).__name__}).") from exc

    if not rows:
        raise CorruptedFileError("The CSV file contains no data rows.")
    return Extraction(total=1, pages=iter([_finish_sheet(1, "", rows, truncated)]))
