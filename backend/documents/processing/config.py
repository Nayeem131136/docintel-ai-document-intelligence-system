"""Tunable limits, read from Django settings at call time (so tests can override them)."""
from django.conf import settings


def max_upload_bytes() -> int:
    return int(getattr(settings, "MAX_UPLOAD_SIZE_MB", 50)) * 1024 * 1024


def max_uncompressed_bytes() -> int:
    """Upper bound on the decompressed size of an XLSX (zip-bomb protection)."""
    return int(getattr(settings, "MAX_UNCOMPRESSED_MB", 500)) * 1024 * 1024


def max_pdf_pages() -> int:
    return int(getattr(settings, "MAX_PDF_PAGES", 5000))


def ocr_dpi() -> int:
    return int(getattr(settings, "OCR_DPI", 200))


def max_spreadsheet_rows() -> int:
    return int(getattr(settings, "MAX_SPREADSHEET_ROWS", 100_000))


# A PDF page with fewer alphanumeric characters than this is treated as scanned.
PDF_MIN_TEXT_CHARS = 25
# Pages mostly covered by an image with little text are also OCR'd.
PDF_IMAGE_COVERAGE = 0.6
PDF_IMAGE_PAGE_TEXT_CHARS = 150
