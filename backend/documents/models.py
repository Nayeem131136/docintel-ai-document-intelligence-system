"""Database schema for DocIntel.

Entity overview (see docs/DATABASE_SCHEMA.md for the diagram):

    Document 1--* DocumentPage        extracted / OCR text per page or sheet
    Document 1--* ExtractionResult    one per invoice found (a 1000-page PDF holds many)
    ExtractionResult 1--* LineItem
    ExtractionResult 1--* ValidationIssue
    ExtractionResult 1--* CorrectionLog
    Document 1--* ProcessingEvent     processing history / audit trail
    CrossVerification *--1 Document   pdf-pdf and pdf-excel comparisons (document_a vs document_b)

Money fields are nullable on purpose: a missing value is stored as NULL and is
never invented or defaulted to zero.
A vector-embedding table for semantic search is added in Phase 5.
"""
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone


def upload_path(instance, filename: str) -> str:
    """Store files under a random name: no collisions, no user-controlled path or name on disk."""
    extension = re.sub(r"[^a-z0-9]", "", Path(filename).suffix.lower())[:8]
    return f"uploads/{timezone.now():%Y/%m/%d}/{uuid.uuid4().hex}" + (f".{extension}" if extension else "")


class Document(models.Model):
    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        IMAGE = "image", "Image (JPG/PNG/TIFF)"
        XLSX = "xlsx", "Excel (XLSX)"
        XLS = "xls", "Excel (XLS)"
        CSV = "csv", "CSV"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        NEEDS_REVIEW = "needs_review", "Needs manual review"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="documents", null=True, blank=True,
                              on_delete=models.SET_NULL)
    original_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to=upload_path)
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True, help_text="Content hash to detect re-uploads.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0, help_text="0-100 progress of the current job.")
    page_count = models.PositiveIntegerField(default=0, help_text="Pages (PDF/image) or sheets (Excel).")
    pages_processed = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0, help_text="Processing attempts (for reprocessing).")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_time_ms = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["status", "-uploaded_at"])]

    def __str__(self) -> str:
        return f"{self.original_filename} [{self.status}]"


class DocumentPage(models.Model):
    """Text of one PDF page, image, or spreadsheet sheet."""

    class Source(models.TextChoices):
        DIGITAL = "digital", "Digital text layer"
        OCR = "ocr", "OCR"
        SPREADSHEET = "spreadsheet", "Spreadsheet"

    document = models.ForeignKey(Document, related_name="pages", on_delete=models.CASCADE)
    page_number = models.PositiveIntegerField(help_text="1-based page / sheet index.")
    sheet_name = models.CharField(max_length=255, blank=True)
    text = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    ocr_confidence = models.FloatField(null=True, blank=True, help_text="Mean OCR confidence 0-1, if OCR was used.")
    table = models.JSONField(
        null=True, blank=True,
        help_text='Spreadsheet rows as {"rows": [[...]], "truncated": bool}; used for PDF-vs-Excel checks.',
    )
    has_error = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, help_text="Error, or a non-fatal warning when has_error is false.")

    class Meta:
        ordering = ["document", "page_number"]
        constraints = [
            models.UniqueConstraint(fields=["document", "page_number"], name="uniq_page_per_document"),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} p{self.page_number}"


class ExtractionResult(models.Model):
    """Structured invoice data. One document can contain several invoices."""

    class Method(models.TextChoices):
        LLM = "llm", "LLM"
        RULES = "rules", "Rule-based fallback"
        MANUAL = "manual", "Manual entry"

    class ReviewStatus(models.TextChoices):
        OK = "ok", "OK"
        NEEDS_REVIEW = "needs_review", "Needs review"
        REVIEWED = "reviewed", "Reviewed / corrected"

    document = models.ForeignKey(Document, related_name="results", on_delete=models.CASCADE)
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)

    invoice_number = models.CharField(max_length=100, null=True, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    supplier_name = models.CharField(max_length=255, null=True, blank=True)
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    currency = models.CharField(max_length=10, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    tax = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    confidence = models.JSONField(default=dict, blank=True, help_text="Per-field confidence 0-1.")
    raw_output = models.JSONField(default=dict, blank=True, help_text="Raw model / parser output for audit.")
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.LLM)
    model_name = models.CharField(max_length=100, blank=True)

    review_status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.OK, db_index=True
    )
    dedupe_key = models.CharField(
        max_length=400, blank=True, db_index=True,
        help_text="Normalised supplier + invoice number, used for duplicate detection.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document", "page_start", "id"]
        indexes = [
            models.Index(fields=["supplier_name"]),
            models.Index(fields=["invoice_number"]),
            models.Index(fields=["invoice_date"]),
        ]

    def __str__(self) -> str:
        return f"Invoice {self.invoice_number or '?'} ({self.supplier_name or 'unknown supplier'})"


class LineItem(models.Model):
    result = models.ForeignKey(ExtractionResult, related_name="line_items", on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)
    description = models.TextField(null=True, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["result", "position"]


class ValidationIssue(models.Model):
    class Severity(models.TextChoices):
        ERROR = "error", "Error"
        WARNING = "warning", "Warning"
        INFO = "info", "Info"

    result = models.ForeignKey(
        ExtractionResult, related_name="issues", null=True, blank=True, on_delete=models.CASCADE
    )
    document = models.ForeignKey(Document, related_name="issues", on_delete=models.CASCADE)
    code = models.CharField(max_length=50, db_index=True, help_text="e.g. MISSING_FIELD, TOTAL_MISMATCH.")
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.ERROR)
    field = models.CharField(max_length=50, blank=True)
    message = models.TextField()
    expected = models.CharField(max_length=100, blank=True)
    found = models.CharField(max_length=100, blank=True)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class CorrectionLog(models.Model):
    """Audit trail of every manual correction."""

    result = models.ForeignKey(ExtractionResult, related_name="corrections", on_delete=models.CASCADE)
    field = models.CharField(max_length=50)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    note = models.TextField(blank=True)
    corrected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-corrected_at"]


class ProcessingEvent(models.Model):
    """Processing history: one row per pipeline stage attempt."""

    class Stage(models.TextChoices):
        UPLOAD = "upload", "Upload"
        TEXT_EXTRACTION = "text_extraction", "Text extraction / OCR"
        AI_EXTRACTION = "ai_extraction", "AI extraction"
        VALIDATION = "validation", "Validation"
        CROSS_VERIFICATION = "cross_verification", "Cross-verification"
        INDEXING = "indexing", "Search indexing"
        REPROCESS = "reprocess", "Reprocess requested"

    class Outcome(models.TextChoices):
        STARTED = "started", "Started"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    document = models.ForeignKey(Document, related_name="events", on_delete=models.CASCADE)
    stage = models.CharField(max_length=30, choices=Stage.choices)
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    message = models.TextField(blank=True)
    duration_ms = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["document", "created_at"])]


class CrossVerification(models.Model):
    """Comparison between two documents (pdf-pdf or pdf-excel)."""

    class CheckType(models.TextChoices):
        PDF_PDF = "pdf_pdf", "PDF vs PDF"
        PDF_EXCEL = "pdf_excel", "PDF vs Excel"

    class Outcome(models.TextChoices):
        MATCH = "match", "Match"
        MISMATCH = "mismatch", "Mismatch"
        INCONCLUSIVE = "inconclusive", "Inconclusive"

    check_type = models.CharField(max_length=20, choices=CheckType.choices)
    document_a = models.ForeignKey(Document, related_name="cross_checks_a", on_delete=models.CASCADE)
    document_b = models.ForeignKey(Document, related_name="cross_checks_b", on_delete=models.CASCADE)
    outcome = models.CharField(max_length=15, choices=Outcome.choices)
    details = models.JSONField(default=dict, blank=True, help_text="Per-field differences.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
