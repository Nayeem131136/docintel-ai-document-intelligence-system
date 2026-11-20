"""AI-extraction stage: segments -> extraction -> grounding -> save -> validation -> cross-check."""
import logging
import time
from decimal import Decimal

from django.db import transaction

from ..models import Document, ExtractionResult, LineItem, ProcessingEvent, ValidationIssue
from .crosscheck import clear_cross_checks, cross_verify_document
from .draft import Draft, Note
from .extractor import extract_segment
from .llm import LLMError, get_llm_client
from .numbers import make_dedupe_key
from .segment import segment_pages
from .tabular import drafts_from_register
from .validation import needs_review, validate_result

logger = logging.getLogger(__name__)
SPREADSHEET_TYPES = ("xlsx", "xls", "csv")
_USE_CONFIGURED = object()


class GuardedLLM:
    """Stops calling the LLM for the rest of a document after repeated failures.

    Avoids waiting through retries on every segment of a 1000-page file when the key is
    wrong or the quota is exhausted: the remaining segments use the rule-based fallback.
    """

    def __init__(self, llm, max_failures: int = 2):
        self.llm = llm
        self.model = getattr(llm, "model", "")
        self.failures = 0
        self.max_failures = max_failures
        self.disabled = False

    def complete_json(self, system: str, user: str) -> dict:
        if self.disabled:
            raise LLMError("AI extraction was turned off for this document after repeated failures.")
        try:
            result = self.llm.complete_json(system, user)
            self.failures = 0
            return result
        except LLMError as exc:
            self.failures += 1
            if not exc.retryable or self.failures >= self.max_failures:
                self.disabled = True
            raise


def _event(document, stage, outcome, message="", duration_ms=None):
    ProcessingEvent.objects.create(document=document, stage=stage, outcome=outcome,
                                   message=message[:2000], duration_ms=duration_ms)


def _fit(value, places: int) -> Decimal | None:
    """Round to the column's scale and drop values too large for NUMERIC(18, n)."""
    if value is None:
        return None
    value = Decimal(value).quantize(Decimal(1).scaleb(-places))
    return value if abs(value) < Decimal(10) ** (18 - places) else None


def _build_drafts(document: Document, llm) -> list[Draft]:
    pages = list(document.pages.filter(has_error=False).order_by("page_number"))
    drafts: list[Draft] = []
    segments_input: list[tuple[int, str]] = []

    for page in pages:
        if document.file_type in SPREADSHEET_TYPES:
            rows = (page.table or {}).get("rows")
            register = drafts_from_register(rows, page.page_number) if rows else None
            if register is not None:
                drafts.extend(register)
                continue
            segments_input = [(page.page_number, page.text)]          # one segment per ordinary sheet
            drafts.extend(_extract_segments(segments_input, llm))
        else:
            segments_input.append((page.page_number, page.text))
    if document.file_type not in SPREADSHEET_TYPES:
        drafts.extend(_extract_segments(segments_input, llm))
    return [d for d in drafts if _looks_like_invoice(d)]


def _looks_like_invoice(draft: Draft) -> bool:
    """A page with no invoice number, no amounts and no line items (a cover letter, say) is not an invoice."""
    return any([draft.invoice_number, draft.total is not None, draft.subtotal is not None, draft.line_items])


def _extract_segments(pages: list[tuple[int, str]], llm) -> list[Draft]:
    drafts = []
    for segment in segment_pages(pages):
        drafts.append(extract_segment(segment.text(), llm, page_start=segment.page_start, page_end=segment.page_end))
    return drafts


def _save_draft(document: Document, draft: Draft) -> ExtractionResult:
    result = ExtractionResult.objects.create(
        document=document,
        page_start=draft.page_start, page_end=draft.page_end,
        invoice_number=(draft.invoice_number or None) and draft.invoice_number[:100],
        invoice_date=draft.invoice_date,
        supplier_name=(draft.supplier_name or None) and draft.supplier_name[:255],
        customer_name=(draft.customer_name or None) and draft.customer_name[:255],
        currency=draft.currency,
        subtotal=_fit(draft.subtotal, 2), tax=_fit(draft.tax, 2), total=_fit(draft.total, 2),
        confidence=draft.confidence, raw_output=draft.raw,
        method=draft.method if draft.method != "table" else ExtractionResult.Method.RULES,
        model_name=draft.model_name,
        dedupe_key=make_dedupe_key(draft.supplier_name, draft.invoice_number),
    )
    LineItem.objects.bulk_create([
        LineItem(result=result, position=index, description=item.get("description"),
                 quantity=_fit(item.get("quantity"), 4), unit_price=_fit(item.get("unit_price"), 4),
                 amount=_fit(item.get("amount"), 2))
        for index, item in enumerate(draft.line_items, start=1)
    ])
    for note in draft.notes:
        ValidationIssue.objects.create(document=document, result=result, code=note.code,
                                       severity=note.severity, field=note.field, message=note.message)
    return result


def _clear_previous(document: Document) -> None:
    clear_cross_checks(document)
    document.results.all().delete()
    document.issues.all().delete()


def run_extraction(document: Document, llm=_USE_CONFIGURED) -> list[ExtractionResult]:
    """Run AI extraction, validation and cross-verification for a document whose text is ready."""
    started = time.perf_counter()
    client = get_llm_client() if llm is _USE_CONFIGURED else llm
    guarded = GuardedLLM(client) if client is not None else None

    _clear_previous(document)
    _event(document, ProcessingEvent.Stage.AI_EXTRACTION, ProcessingEvent.Outcome.STARTED,
           "LLM extraction" if guarded else "Rule-based extraction (no LLM configured)")
    document.progress = max(document.progress, 60)
    document.save(update_fields=["progress", "updated_at"])

    try:
        drafts = _build_drafts(document, guarded)
        with transaction.atomic():
            results = [_save_draft(document, draft) for draft in drafts]
    except Exception:
        _event(document, ProcessingEvent.Stage.AI_EXTRACTION, ProcessingEvent.Outcome.FAILED,
               "Extraction crashed", int((time.perf_counter() - started) * 1000))
        raise
    methods = sorted({r.method for r in results}) or ["none"]
    _event(document, ProcessingEvent.Stage.AI_EXTRACTION, ProcessingEvent.Outcome.SUCCESS,
           f"{len(results)} invoice(s) found using {', '.join(methods)}", int((time.perf_counter() - started) * 1000))
    document.progress = 80
    document.save(update_fields=["progress", "updated_at"])

    # ---- validation ----------------------------------------------------------------
    validation_started = time.perf_counter()
    for result in results:
        issues = validate_result(result)
        for issue in issues:
            ValidationIssue.objects.create(document=document, result=result, **issue)
        existing = result.issues.filter(severity__in=("error", "warning")).exists()
        result.review_status = (ExtractionResult.ReviewStatus.NEEDS_REVIEW
                                if existing or needs_review(issues) else ExtractionResult.ReviewStatus.OK)
        result.save(update_fields=["review_status", "updated_at"])

    if not results:
        ValidationIssue.objects.create(
            document=document, code="NO_INVOICE_FOUND", severity="error",
            message="No invoice data could be found in this document.")
    duplicate = (Document.objects.filter(sha256=document.sha256).exclude(pk=document.pk)
                 .filter(uploaded_at__lte=document.uploaded_at).order_by("uploaded_at").first())
    if duplicate:
        ValidationIssue.objects.create(
            document=document, code="DUPLICATE_FILE", severity="warning", field="file",
            message=f"This file is identical to '{duplicate.original_filename}' that was uploaded earlier.",
            found=f"document {duplicate.pk}")
    _event(document, ProcessingEvent.Stage.VALIDATION, ProcessingEvent.Outcome.SUCCESS,
           f"{sum(r.review_status == 'needs_review' for r in results)} of {len(results)} invoice(s) need review",
           int((time.perf_counter() - validation_started) * 1000))
    document.progress = 90
    document.save(update_fields=["progress", "updated_at"])

    # ---- cross-verification ---------------------------------------------------------------
    cross_started = time.perf_counter()
    checks = cross_verify_document(document)
    _event(document, ProcessingEvent.Stage.CROSS_VERIFICATION, ProcessingEvent.Outcome.SUCCESS,
           f"{len(checks)} cross-check(s): " + (", ".join(sorted({c.outcome for c in checks})) or "none"),
           int((time.perf_counter() - cross_started) * 1000))
    return results


def final_status(document: Document) -> str:
    """COMPLETED only when nothing needs a human: no failed pages, no flagged results."""
    document.refresh_from_db(fields=["status"])
    flagged = (document.results.filter(review_status=ExtractionResult.ReviewStatus.NEEDS_REVIEW).exists()
               or not document.results.exists()
               or document.pages.filter(has_error=True).exists()
               or document.issues.filter(result__isnull=True, resolved=False, severity__in=("error", "warning")).exists())
    return Document.Status.NEEDS_REVIEW if flagged else Document.Status.COMPLETED
