"""PDF extraction: digital text layer first, OCR only for pages that need it.

Processes one page at a time (streaming) so a ~1000-page PDF never has to sit in
memory, and a single bad page does not fail the whole document.
"""
import logging

import pymupdf
from PIL import Image

from . import config
from .base import Extraction, PageResult, clean_text
from .errors import CorruptedFileError, FileTooLargeError, PasswordProtectedError
from .ocr import ocr_image

logger = logging.getLogger(__name__)


def _alnum_count(text: str) -> int:
    return sum(1 for ch in text if ch.isalnum())


def _image_coverage(page) -> float:
    """Fraction of the page area covered by embedded images (scanned pages are ~1.0)."""
    try:
        page_area = abs(page.rect.width * page.rect.height) or 1.0
        covered = sum(abs(info["bbox"][2] - info["bbox"][0]) * abs(info["bbox"][3] - info["bbox"][1])
                      for info in page.get_image_info())
        return min(1.0, covered / page_area)
    except Exception:  # noqa: BLE001 - coverage is only a heuristic
        return 0.0


def _is_blank(page, text: str) -> bool:
    """No text, no images and no vector drawings: nothing to OCR."""
    if text.strip():
        return False
    try:
        return not page.get_images() and not page.get_drawings()
    except Exception:  # noqa: BLE001
        return False


def _needs_ocr(page, text: str) -> bool:
    chars = _alnum_count(text)
    if chars >= config.PDF_MIN_TEXT_CHARS:
        # Has a text layer. Still OCR when the page is basically one big picture
        # with only a tiny text stamp (e.g. a scan with a "page 3" footer).
        return chars < config.PDF_IMAGE_PAGE_TEXT_CHARS and _image_coverage(page) > config.PDF_IMAGE_COVERAGE
    return not _is_blank(page, text)


def _ocr_page(page) -> tuple[str, float | None]:
    pixmap = page.get_pixmap(dpi=config.ocr_dpi(), alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    result = ocr_image(image)
    return result.text, result.confidence


def _open(path: str) -> "pymupdf.Document":
    try:
        document = pymupdf.open(path)
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises several error types
        raise CorruptedFileError(f"The PDF could not be opened (corrupted or invalid) ({type(exc).__name__}).") from exc
    if document.needs_pass:
        document.close()
        raise PasswordProtectedError("The PDF is password-protected and cannot be read.")
    if document.page_count == 0:
        document.close()
        raise CorruptedFileError("The PDF has no pages.")
    if document.page_count > config.max_pdf_pages():
        count = document.page_count
        document.close()
        raise FileTooLargeError(f"The PDF has {count} pages; the limit is {config.max_pdf_pages()}.")
    return document


def extract_pdf(path: str) -> Extraction:
    document = _open(path)
    total = document.page_count

    def pages():
        try:
            for index in range(total):
                number = index + 1
                try:
                    page = document.load_page(index)
                    text = page.get_text("text", sort=True)
                    if _needs_ocr(page, text):
                        ocr_text, confidence = _ocr_page(page)
                        # Keep the digital text if it is longer than what OCR produced.
                        if len(ocr_text) >= len(text.strip()):
                            yield PageResult(number, clean_text(ocr_text), "ocr", confidence)
                            continue
                    yield PageResult(number, clean_text(text), "digital")
                except Exception as exc:  # noqa: BLE001 - isolate a bad page
                    logger.warning("PDF page %s failed: %s", number, exc)
                    yield PageResult(number, source="digital", error=f"Page could not be read ({type(exc).__name__}).")
        finally:
            document.close()

    return Extraction(total=total, pages=pages())
