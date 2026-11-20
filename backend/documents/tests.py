from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import (
    CorrectionLog,
    CrossVerification,
    Document,
    DocumentPage,
    ExtractionResult,
    LineItem,
    ProcessingEvent,
    ValidationIssue,
)


def make_document(name="invoice.pdf", file_type=Document.FileType.PDF, sha="a" * 64):
    return Document.objects.create(
        original_filename=name, file=f"uploads/{name}", file_type=file_type, size_bytes=10, sha256=sha
    )


class HealthEndpointTests(TestCase):
    def test_health_reports_ok(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "ok")


class SchemaTests(TestCase):
    def test_new_document_defaults_to_queued(self):
        doc = make_document()
        self.assertEqual(doc.status, Document.Status.QUEUED)
        self.assertEqual(doc.progress, 0)
        self.assertEqual(doc.attempts, 0)

    def test_missing_fields_stay_null_not_invented(self):
        """A result with nothing extracted must keep NULLs (never 0 or '')."""
        result = ExtractionResult.objects.create(document=make_document())
        result.refresh_from_db()
        for field in ("invoice_number", "invoice_date", "supplier_name", "customer_name",
                      "currency", "subtotal", "tax", "total"):
            self.assertIsNone(getattr(result, field), field)

    def test_one_document_can_hold_many_invoices_with_line_items(self):
        doc = make_document()
        first = ExtractionResult.objects.create(
            document=doc, page_start=1, page_end=1, invoice_number="INV-1",
            invoice_date=date(2026, 1, 5), supplier_name="Acme Ltd", total=Decimal("115.00"),
        )
        ExtractionResult.objects.create(document=doc, page_start=2, page_end=3, invoice_number="INV-2")
        LineItem.objects.create(result=first, position=1, description="Widget",
                                quantity=Decimal("2"), unit_price=Decimal("50"), amount=Decimal("100.00"))
        self.assertEqual(doc.results.count(), 2)
        self.assertEqual(first.line_items.get().amount, Decimal("100.00"))

    def test_page_number_unique_per_document(self):
        doc = make_document()
        DocumentPage.objects.create(document=doc, page_number=1, text="a", source="digital")
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentPage.objects.create(document=doc, page_number=1, text="b", source="ocr")

    def test_history_issues_corrections_and_cross_checks(self):
        doc_a = make_document("a.pdf", sha="b" * 64)
        doc_b = make_document("b.xlsx", Document.FileType.XLSX, sha="c" * 64)
        result = ExtractionResult.objects.create(document=doc_a, invoice_number="X")
        ProcessingEvent.objects.create(document=doc_a, stage="text_extraction", outcome="success", duration_ms=120)
        ValidationIssue.objects.create(document=doc_a, result=result, code="TOTAL_MISMATCH", message="m")
        CorrectionLog.objects.create(result=result, field="total", old_value="1", new_value="2")
        CrossVerification.objects.create(
            check_type="pdf_excel", document_a=doc_a, document_b=doc_b, outcome="mismatch",
            details={"total": {"pdf": "10.00", "excel": "12.00"}},
        )
        self.assertEqual(doc_a.events.count(), 1)
        self.assertEqual(doc_a.issues.count(), 1)
        self.assertEqual(result.corrections.count(), 1)
        self.assertEqual(CrossVerification.objects.count(), 1)

    def test_deleting_document_cascades(self):
        doc = make_document()
        result = ExtractionResult.objects.create(document=doc)
        LineItem.objects.create(result=result, position=1)
        doc.delete()
        self.assertEqual(ExtractionResult.objects.count(), 0)
        self.assertEqual(LineItem.objects.count(), 0)
