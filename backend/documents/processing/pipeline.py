"""Text-extraction pipeline: validates a file, extracts every page, and records the history.

``extract_document_text`` is the entry point; the orchestrator and CLI call it as the
first stage of the full pipeline (text -> AI extraction -> validation -> indexing).
"""
import hashlib
import logging
import time
from pathlib import Path

from django.core.files import File
from django.utils import timezone

from ..models import Document, DocumentPage, ProcessingEvent
from .base import Extraction, clean_text
from .detect import detect_file_type
from .errors import ProcessingError
from .image import extract_image
from .pdf import extract_pdf
from .spreadsheet import extract_csv, extract_xls, extract_xlsx

logger = logging.getLogger(__name__)

EXTRACTORS = {
    "pdf": extract_pdf,
    "image": extract_image,
    "xlsx": extract_xlsx,
    "xls": extract_xls,
    "csv": extract_csv,
}

BATCH_SIZE = 20   # pages written to the database per round trip


def sha256_of(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_document_from_path(path: str | Path, original_filename: str | None = None, owner=None) -> Document:
    """Validate a local file and store it as a QUEUED Document.

    Raises ProcessingError subclasses for unsupported / empty / oversized files,
    so callers (the API, the CLI) can reject them up front.
    """
    path = Path(path)
    name = original_filename or path.name
    file_type = detect_file_type(path, name)
    with open(path, "rb") as handle:
        document = Document(
            owner=owner,
            original_filename=name[:255],
            file_type=file_type,
            size_bytes=path.stat().st_size,
            sha256=sha256_of(path),
        )
        document.file.save(name, File(handle), save=False)
    document.save()
    ProcessingEvent.objects.create(
        document=document, stage=ProcessingEvent.Stage.UPLOAD, outcome=ProcessingEvent.Outcome.SUCCESS,
        message=f"Stored {document.size_bytes} bytes as {file_type}.",
    )
    return document


def _event(document: Document, stage: str, outcome: str, message: str = "", duration_ms: int | None = None):
    return ProcessingEvent.objects.create(
        document=document, stage=stage, outcome=outcome, message=message[:2000], duration_ms=duration_ms
    )


def _store_pages(document: Document, extraction: Extraction, progress_cap: int = 99) -> tuple[int, int]:
    """Write pages in batches, updating progress. Returns (pages_ok, pages_failed)."""
    ok = failed = 0
    batch: list[DocumentPage] = []

    def flush():
        if batch:
            DocumentPage.objects.bulk_create(batch)
            batch.clear()
        done = ok + failed
        document.pages_processed = done
        document.progress = min(progress_cap, int(progress_cap * done / max(1, extraction.total)))
        document.save(update_fields=["pages_processed", "progress", "updated_at"])

    for page in extraction.pages:
        if page.has_error:
            failed += 1
        else:
            ok += 1
        batch.append(
            DocumentPage(
                document=document,
                page_number=page.page_number,
                sheet_name=page.sheet_name,
                text=clean_text(page.text),
                source=page.source,
                ocr_confidence=page.ocr_confidence,
                table=page.table,
                has_error=page.has_error,
                error_message=page.error or page.warning,
            )
        )
        if len(batch) >= BATCH_SIZE:
            flush()
    flush()
    return ok, failed


def extract_document_text(document: Document, finalize: bool = True) -> Document:
    """Run text extraction / OCR / spreadsheet parsing for one document.

    With ``finalize=False`` (used by the full pipeline) a successful run leaves the
    status as PROCESSING so the AI-extraction stage can continue; failures are final.

    Safe to call again (reprocessing): previous pages are replaced and the attempt
    counter increases. Never raises for expected failures; the document is marked
    FAILED with a readable message instead.
    """
    started = time.perf_counter()
    document.pages.all().delete()
    document.status = Document.Status.PROCESSING
    document.progress = 0
    document.pages_processed = 0
    document.page_count = 0
    document.error_message = ""
    document.attempts += 1
    document.save()
    _event(document, ProcessingEvent.Stage.TEXT_EXTRACTION, ProcessingEvent.Outcome.STARTED,
           f"Attempt {document.attempts}")

    try:
        file_type = detect_file_type(document.file.path, document.original_filename)
        if file_type != document.file_type:
            document.file_type = file_type
        extraction = EXTRACTORS[file_type](document.file.path)
        document.page_count = extraction.total
        document.save(update_fields=["file_type", "page_count", "updated_at"])

        ok, failed = _store_pages(document, extraction, progress_cap=99 if finalize else 55)

        if ok == 0:
            raise ProcessingError(f"None of the {failed} page(s) could be read.")
        if finalize:
            document.status = Document.Status.NEEDS_REVIEW if failed else Document.Status.COMPLETED
            document.progress = 100
        else:
            document.progress = 55
        if failed:
            document.error_message = f"{failed} of {extraction.total} page(s) could not be read."
        outcome, message = ProcessingEvent.Outcome.SUCCESS, f"{ok} page(s) extracted, {failed} failed."
    except ProcessingError as exc:
        logger.warning("Document %s failed: %s (cause: %r)", document.pk, exc, exc.__cause__)
        document.status = Document.Status.FAILED
        document.error_message = str(exc)[:2000]
        outcome, message = ProcessingEvent.Outcome.FAILED, str(exc)
    except Exception as exc:  # noqa: BLE001 - last line of defence: never crash the worker
        logger.exception("Unexpected failure processing document %s", document.pk)
        document.status = Document.Status.FAILED
        document.error_message = f"Unexpected error while processing ({type(exc).__name__})."
        outcome, message = ProcessingEvent.Outcome.FAILED, document.error_message

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    document.processing_time_ms = elapsed_ms
    document.processed_at = timezone.now()
    document.save()
    _event(document, ProcessingEvent.Stage.TEXT_EXTRACTION, outcome, message, elapsed_ms)
    return document
