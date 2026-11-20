"""The complete pipeline for one document:
text extraction / OCR  ->  AI extraction  ->  validation  ->  cross-verification.

Phase 4 runs ``process_document`` inside a Celery task.
"""
import logging
import time

from django.utils import timezone

from .extraction.service import _USE_CONFIGURED, final_status, run_extraction
from .models import Document, ProcessingEvent
from .processing.pipeline import extract_document_text

logger = logging.getLogger(__name__)


def process_document(document: Document, llm=_USE_CONFIGURED) -> Document:
    """Process a document end to end. Expected failures never raise; they mark the document FAILED."""
    started = time.perf_counter()
    extract_document_text(document, finalize=False)
    if document.status == Document.Status.FAILED:
        return document

    try:
        run_extraction(document, llm=llm)
        document.status = final_status(document)
        document.progress = 100
        document.error_message = ""
        failed_pages = document.pages.filter(has_error=True).count()
        if failed_pages:
            document.error_message = f"{failed_pages} of {document.page_count} page(s) could not be read."
    except Exception as exc:  # noqa: BLE001 - never crash the worker
        logger.exception("Extraction failed for document %s", document.pk)
        document.status = Document.Status.FAILED
        document.error_message = f"Unexpected error during extraction ({type(exc).__name__})."
        ProcessingEvent.objects.create(document=document, stage=ProcessingEvent.Stage.AI_EXTRACTION,
                                       outcome=ProcessingEvent.Outcome.FAILED, message=document.error_message)

    document.processing_time_ms = int((time.perf_counter() - started) * 1000)
    document.processed_at = timezone.now()
    document.save()
    return document
