"""Validation rules for extracted invoices. Every finding becomes a ValidationIssue.

A result is flagged "needs review" when it has any error or warning; "info" findings
(e.g. no subtotal to check against) never block it.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from ..models import DocumentPage, ExtractionResult

TOLERANCE = Decimal("0.02")        # rounding slack for money comparisons
SPREADSHEET_TYPES = ("xlsx", "xls", "csv")

REQUIRED_FIELDS = ("invoice_number", "invoice_date", "supplier_name", "total")   # missing => error
WARNING_FIELDS = ("currency", "customer_name")                                   # missing => warning
INFO_FIELDS = ("subtotal", "tax")                                                # missing => info
LABELS = {
    "invoice_number": "invoice number", "invoice_date": "invoice date", "supplier_name": "supplier",
    "customer_name": "customer", "currency": "currency", "subtotal": "subtotal", "tax": "tax", "total": "total",
}


def low_ocr_threshold() -> float:
    return float(getattr(settings, "LOW_OCR_CONFIDENCE", 0.80))


def _issue(code, severity, message, field="", expected="", found=""):
    return {"code": code, "severity": severity, "field": field, "message": message,
            "expected": str(expected), "found": str(found)}


def _differs(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) > TOLERANCE


def validate_result(result: ExtractionResult) -> list[dict]:
    issues: list[dict] = []

    # --- missing fields --------------------------------------------------------
    for name in REQUIRED_FIELDS:
        if getattr(result, name) in (None, ""):
            issues.append(_issue("MISSING_FIELD", "error", f"The {LABELS[name]} is missing.", name))
    for name in WARNING_FIELDS:
        if getattr(result, name) in (None, ""):
            issues.append(_issue("MISSING_FIELD", "warning", f"The {LABELS[name]} is missing.", name))
    for name in INFO_FIELDS:
        if getattr(result, name) is None:
            issues.append(_issue("MISSING_FIELD", "info", f"The {LABELS[name]} was not found.", name))

    # --- sanity ------------------------------------------------------------------
    for name in ("subtotal", "tax", "total"):
        value = getattr(result, name)
        if value is not None and value < 0:
            issues.append(_issue("NEGATIVE_AMOUNT", "warning",
                                 f"The {LABELS[name]} is negative ({value}); this may be a credit note.", name, found=value))
    if result.invoice_date:
        if result.invoice_date > timezone.now().date() + timedelta(days=1):
            issues.append(_issue("FUTURE_DATE", "warning", f"The invoice date {result.invoice_date} is in the future.",
                                 "invoice_date", found=result.invoice_date))
        elif result.invoice_date < date(1990, 1, 1):
            issues.append(_issue("OLD_DATE", "warning", f"The invoice date {result.invoice_date} is implausibly old.",
                                 "invoice_date", found=result.invoice_date))

    # --- line items ----------------------------------------------------------------
    items = list(result.line_items.all())
    for item in items:
        if None not in (item.quantity, item.unit_price, item.amount):
            expected = (item.quantity * item.unit_price).quantize(Decimal("0.01"))
            if _differs(expected, item.amount):
                issues.append(_issue(
                    "LINE_ITEM_MISMATCH", "error",
                    f"Line {item.position}: quantity x unit price is {expected} but the amount is {item.amount}.",
                    f"line_items[{item.position}]", expected, item.amount))
    amounts = [i.amount for i in items]
    lines_sum = sum(amounts, Decimal(0)) if items and all(a is not None for a in amounts) else None

    # --- totals ----------------------------------------------------------------------
    subtotal, tax, total = result.subtotal, result.tax, result.total
    if lines_sum is not None and subtotal is not None and _differs(lines_sum, subtotal):
        issues.append(_issue("SUBTOTAL_MISMATCH", "error",
                             f"The line items add up to {lines_sum} but the subtotal is {subtotal}.",
                             "subtotal", lines_sum, subtotal))
    base = subtotal if subtotal is not None else lines_sum
    if total is not None:
        if base is None:
            issues.append(_issue("NOT_VERIFIABLE", "info",
                                 "The total could not be verified: no subtotal or line items were found.", "total"))
        elif tax is not None:
            expected = base + tax
            if _differs(expected, total):
                issues.append(_issue("TOTAL_MISMATCH", "error",
                                     f"Subtotal {base} + tax {tax} = {expected}, but the total is {total}.",
                                     "total", expected, total))
        elif _differs(base, total):
            issues.append(_issue("TOTAL_MISMATCH", "warning",
                                 f"The total {total} differs from the subtotal {base} and no tax amount was found.",
                                 "total", base, total))
    if tax is not None and subtotal is not None and subtotal > 0 and tax > subtotal:
        issues.append(_issue("TAX_EXCEEDS_SUBTOTAL", "warning",
                             f"The tax {tax} is larger than the subtotal {subtotal}.", "tax", subtotal, tax))

    # --- source quality ------------------------------------------------------------------
    pages = DocumentPage.objects.filter(document=result.document)
    if result.page_start is not None:
        pages = pages.filter(page_number__gte=result.page_start, page_number__lte=result.page_end or result.page_start)
    confidences = [p.ocr_confidence for p in pages if p.ocr_confidence is not None]
    if confidences and sum(confidences) / len(confidences) < low_ocr_threshold():
        mean = sum(confidences) / len(confidences)
        issues.append(_issue("LOW_OCR_CONFIDENCE", "warning",
                             f"The scan was read with low confidence ({mean:.0%}); please check the values.",
                             found=f"{mean:.2f}", expected=f">= {low_ocr_threshold():.2f}"))
    if pages.filter(has_error=True).exists():
        issues.append(_issue("PAGE_READ_ERROR", "warning", "Some pages of this invoice could not be read."))

    # --- duplicates --------------------------------------------------------------------------
    if result.dedupe_key:
        # The same invoice in a PDF *and* a spreadsheet is a cross-verification pair, not a duplicate.
        is_sheet = result.document.file_type in SPREADSHEET_TYPES
        earlier = next(
            (c for c in ExtractionResult.objects.filter(dedupe_key=result.dedupe_key, pk__lt=result.pk)
             .exclude(pk=result.pk).select_related("document").order_by("pk")
             if (c.document.file_type in SPREADSHEET_TYPES) == is_sheet), None)
        if earlier:
            where = ("in the same file" if earlier.document_id == result.document_id
                     else f"in '{earlier.document.original_filename}'")
            severity = "error" if result.supplier_name else "warning"
            issues.append(_issue("DUPLICATE_INVOICE", severity,
                                 f"Invoice {result.invoice_number} appears to be a duplicate of one already "
                                 f"processed {where}.", "invoice_number", found=f"result {earlier.pk}"))
    return issues


def needs_review(issues: list[dict]) -> bool:
    return any(i["severity"] in ("error", "warning") for i in issues)
