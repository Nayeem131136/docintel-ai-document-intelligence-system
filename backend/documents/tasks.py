"""Celery tasks: OCR and AI work runs in background workers, never in the web request."""
import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import InterfaceError, OperationalError, transaction
from django.utils import timezone

from .models import Document, ProcessingEvent
from .orchestrator import process_document

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="documents.process_document",
    acks_late=True,                                   # an unfinished task is redelivered if a worker dies
    autoretry_for=(OperationalError, InterfaceError),  # transient database outage
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    time_limit=settings.CELERY_TASK_TIME_LIMIT,
)
def process_document_task(self, document_id: str) -> str:
    document = Document.objects.filter(pk=document_id).first()
    if document is None:
        return "missing"          # deleted while queued

    # Claim the job: only one worker may start a QUEUED document, so a duplicate message is a no-op.
    claimed = Document.objects.filter(pk=document_id, status=Document.Status.QUEUED).update(
        status=Document.Status.PROCESSING)
    if not claimed:
        redelivered = bool((self.request.delivery_info or {}).get("redelivered"))
        if not (redelivered and document.status == Document.Status.PROCESSING):
            return f"skipped ({document.status})"
    document.refresh_from_db()

    try:
        process_document(document)
    except SoftTimeLimitExceeded:
        _mark_failed(document_id, "Processing took too long and was stopped. Try reprocessing.")
        return "timeout"
    return document.status


def _mark_failed(document_id: str, message: str) -> None:
    Document.objects.filter(pk=document_id).update(status=Document.Status.FAILED, error_message=message,
                                                   processed_at=timezone.now())
    ProcessingEvent.objects.create(document_id=document_id, stage=ProcessingEvent.Stage.TEXT_EXTRACTION,
                                   outcome=ProcessingEvent.Outcome.FAILED, message=message)


def enqueue_document(document: Document) -> None:
    """Queue a document once the surrounding transaction commits (so the worker can see the row)."""

    def send():
        try:
            process_document_task.delay(str(document.pk))
        except Exception:  # noqa: BLE001 - broker down: leave a clear, recoverable state
            logger.exception("Could not queue document %s", document.pk)
            _mark_failed(str(document.pk), "The document could not be queued for processing. "
                                           "It can be reprocessed once the service recovers.")

    transaction.on_commit(send)
