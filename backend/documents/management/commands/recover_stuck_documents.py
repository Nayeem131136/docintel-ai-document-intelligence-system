"""Recover documents left behind by a crashed worker or an outage.

    python manage.py recover_stuck_documents --minutes 120

* PROCESSING for longer than the limit -> marked FAILED (can be reprocessed from the API)
* QUEUED for longer than the limit      -> queued again
Run it from cron or after a restart. It is safe to run repeatedly.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from documents.models import Document, ProcessingEvent
from documents.tasks import enqueue_document


class Command(BaseCommand):
    help = "Mark stalled PROCESSING documents as failed and re-queue stalled QUEUED ones."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=120)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=options["minutes"])
        failed = requeued = 0
        for document in Document.objects.filter(status=Document.Status.PROCESSING, updated_at__lt=cutoff):
            document.status = Document.Status.FAILED
            document.error_message = "Processing was interrupted and did not finish. You can reprocess this document."
            document.save(update_fields=["status", "error_message", "updated_at"])
            ProcessingEvent.objects.create(document=document, stage=ProcessingEvent.Stage.TEXT_EXTRACTION,
                                           outcome=ProcessingEvent.Outcome.FAILED, message=document.error_message)
            failed += 1
        for document in Document.objects.filter(status=Document.Status.QUEUED, updated_at__lt=cutoff):
            with transaction.atomic():
                document.save(update_fields=["updated_at"])
                enqueue_document(document)
            requeued += 1
        self.stdout.write(f"Marked {failed} stalled document(s) as failed; re-queued {requeued}.")
