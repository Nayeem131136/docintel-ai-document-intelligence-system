"""Cross-verification: compare the same invoice found in two different documents.

  * pdf_pdf    - PDF / scan against another PDF / scan
  * pdf_excel  - PDF / scan against an Excel or CSV file

Invoices are paired by invoice number (and a matching supplier or equal total, so two
suppliers who both use "INV-001" are not confused). Disagreements are stored in
CrossVerification and raised as CROSS_CHECK_MISMATCH issues on both results.
"""
import re
from decimal import Decimal

from ..models import CrossVerification, Document, ExtractionResult, ValidationIssue
from .numbers import alnum

SPREADSHEET_TYPES = {Document.FileType.XLSX, Document.FileType.XLS, Document.FileType.CSV}
TOLERANCE = Decimal("0.01")
_SUFFIXES = re.compile(r"\b(ltd|limited|inc|incorporated|llc|llp|co|corp|corporation|plc|pvt|private|company)\b")
MONEY_FIELDS = ("subtotal", "tax", "total")


def _supplier_key(name: str | None) -> str:
    return alnum(_SUFFIXES.sub(" ", (name or "").casefold().replace(".", "")))


def _same_supplier(a: str | None, b: str | None) -> bool:
    ka, kb = _supplier_key(a), _supplier_key(b)
    return bool(ka and kb and (ka == kb or ka in kb or kb in ka))


def _is_same_invoice(a: ExtractionResult, b: ExtractionResult) -> bool:
    if alnum(a.invoice_number) != alnum(b.invoice_number):
        return False
    if not a.supplier_name or not b.supplier_name:
        return True
    return _same_supplier(a.supplier_name, b.supplier_name) or (
        a.total is not None and b.total is not None and abs(a.total - b.total) <= TOLERANCE)


def compare_results(a: ExtractionResult, b: ExtractionResult) -> dict:
    fields: dict[str, dict] = {}

    def add(name, left, right, equal):
        fields[name] = {"a": None if left is None else str(left), "b": None if right is None else str(right),
                        "match": bool(equal)}

    if a.supplier_name and b.supplier_name:
        add("supplier_name", a.supplier_name, b.supplier_name, _same_supplier(a.supplier_name, b.supplier_name))
    if a.customer_name and b.customer_name:
        add("customer_name", a.customer_name, b.customer_name, _same_supplier(a.customer_name, b.customer_name))
    if a.invoice_date and b.invoice_date:
        add("invoice_date", a.invoice_date, b.invoice_date, a.invoice_date == b.invoice_date)
    if a.currency and b.currency:
        add("currency", a.currency, b.currency, a.currency.upper() == b.currency.upper())
    for name in MONEY_FIELDS:
        left, right = getattr(a, name), getattr(b, name)
        if left is not None and right is not None:
            add(name, left, right, abs(left - right) <= TOLERANCE)
    items_a, items_b = list(a.line_items.all()), list(b.line_items.all())
    if items_a and items_b:
        add("line_item_count", len(items_a), len(items_b), len(items_a) == len(items_b))

    if not fields:
        outcome = CrossVerification.Outcome.INCONCLUSIVE
    elif all(f["match"] for f in fields.values()):
        outcome = CrossVerification.Outcome.MATCH
    else:
        outcome = CrossVerification.Outcome.MISMATCH
    return {"invoice_number": a.invoice_number, "result_a": a.pk, "result_b": b.pk,
            "outcome": outcome, "fields": fields}


def _check_type(a: Document, b: Document) -> str | None:
    spreadsheets = (a.file_type in SPREADSHEET_TYPES) + (b.file_type in SPREADSHEET_TYPES)
    if spreadsheets == 2:
        return None          # spreadsheet vs spreadsheet is not a supported check
    return CrossVerification.CheckType.PDF_EXCEL if spreadsheets == 1 else CrossVerification.CheckType.PDF_PDF


def clear_cross_checks(document: Document) -> None:
    """Remove stale cross-check data before a document is (re)processed."""
    CrossVerification.objects.filter(document_a=document).delete()
    CrossVerification.objects.filter(document_b=document).delete()
    ValidationIssue.objects.filter(code="CROSS_CHECK_MISMATCH", found__contains=str(document.pk)).delete()


def cross_verify_document(document: Document) -> list[CrossVerification]:
    mine = list(document.results.exclude(invoice_number__isnull=True).exclude(invoice_number=""))
    others: dict = {}
    for result in mine:
        for other in (ExtractionResult.objects.filter(invoice_number__iexact=result.invoice_number)
                      .exclude(document=document).select_related("document")):
            if _is_same_invoice(result, other):
                others.setdefault(other.document_id, {"document": other.document, "pairs": []})["pairs"].append(
                    (result, other))

    created: list[CrossVerification] = []
    for entry in others.values():
        other_doc: Document = entry["document"]
        check_type = _check_type(document, other_doc)
        if check_type is None:
            continue
        doc_a, doc_b = sorted([document, other_doc], key=lambda d: (d.uploaded_at, str(d.pk)))
        comparisons = []
        for mine_result, other_result in entry["pairs"]:
            first, second = (mine_result, other_result) if doc_a.pk == document.pk else (other_result, mine_result)
            comparisons.append(compare_results(first, second))
        outcomes = {c["outcome"] for c in comparisons}
        outcome = (CrossVerification.Outcome.MISMATCH if CrossVerification.Outcome.MISMATCH in outcomes
                   else CrossVerification.Outcome.MATCH if CrossVerification.Outcome.MATCH in outcomes
                   else CrossVerification.Outcome.INCONCLUSIVE)
        check, _ = CrossVerification.objects.update_or_create(
            document_a=doc_a, document_b=doc_b,
            defaults={"check_type": check_type, "outcome": outcome, "details": {"invoices": comparisons}})
        created.append(check)

        if outcome == CrossVerification.Outcome.MISMATCH:
            _flag_mismatches(document, other_doc, comparisons)
    return created


def _flag_mismatches(document: Document, other_doc: Document, comparisons: list[dict]) -> None:
    for comparison in comparisons:
        if comparison["outcome"] != CrossVerification.Outcome.MISMATCH:
            continue
        differing = [name.replace("_", " ") for name, f in comparison["fields"].items() if not f["match"]]
        for result in ExtractionResult.objects.filter(pk__in=[comparison["result_a"], comparison["result_b"]]):
            counterpart = other_doc if result.document_id == document.pk else document
            found = f"document {counterpart.pk}"
            if ValidationIssue.objects.filter(result=result, code="CROSS_CHECK_MISMATCH", found=found,
                                              resolved=False).exists():
                continue
            ValidationIssue.objects.create(
                document=result.document, result=result, code="CROSS_CHECK_MISMATCH", severity="error",
                message=(f"Invoice {comparison['invoice_number']} does not match '{counterpart.original_filename}': "
                         f"{', '.join(differing)} differ."),
                found=found)
            if result.review_status == ExtractionResult.ReviewStatus.OK:
                result.review_status = ExtractionResult.ReviewStatus.NEEDS_REVIEW
                result.save(update_fields=["review_status", "updated_at"])
            if (result.document.status == Document.Status.COMPLETED):
                result.document.status = Document.Status.NEEDS_REVIEW
                result.document.save(update_fields=["status", "updated_at"])
