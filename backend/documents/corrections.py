
"""Manual corrections: apply a reviewer's edits, keep an audit trail, and re-validate."""
import json
from decimal import Decimal

from django.db import transaction

from .extraction.crosscheck import clear_cross_checks, cross_verify_document
from .extraction.numbers import make_dedupe_key
from .extraction.service import final_status
from .extraction.validation import validate_result
from .search.indexer import safe_index_result
from .models import CorrectionLog, Document, ExtractionResult, LineItem, ValidationIssue

SCALAR_FIELDS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "currency",
    "subtotal",
    "discount",
    "tax",
    "total",
)


def _text(value) -> str:
    if value is None:
        return ""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _normalise(name: str, value):
    if isinstance(value, str):
        value = " ".join(value.split()) or None
        if value and name == "currency":
            value = value.upper()
    return value


def _lines_snapshot(items) -> str:
    return json.dumps(
        [
            {
                "description": i.description,
                "quantity": _text(i.quantity),
                "unit_price": _text(i.unit_price),
                "amount": _text(i.amount),
            }
            for i in items
        ],
        ensure_ascii=False,
    )


def refresh_review_state(result: ExtractionResult) -> None:
    """needs_review while unresolved errors/warnings exist, otherwise ok (a human approval is kept)."""
    if result.review_status == ExtractionResult.ReviewStatus.REVIEWED:
        return
    flagged = result.issues.filter(
        resolved=False, severity__in=("error", "warning")
    ).exists()
    result.review_status = (
        ExtractionResult.ReviewStatus.NEEDS_REVIEW
        if flagged
        else ExtractionResult.ReviewStatus.OK
    )
    result.save(update_fields=["review_status", "updated_at"])


def update_document_status(document: Document) -> None:
    """Recompute completed / needs_review. Documents that are queued, processing or failed are left alone."""
    document.refresh_from_db(fields=["status"])
    if document.status in (
        Document.Status.COMPLETED,
        Document.Status.NEEDS_REVIEW,
    ):
        document.status = final_status(document)
        document.save(update_fields=["status", "updated_at"])


def revalidate(result: ExtractionResult) -> None:
    """Rebuild this result's validation issues and cross-checks after its values changed."""
    document = result.document
    affected_ids = set(
        ValidationIssue.objects.filter(
            code="CROSS_CHECK_MISMATCH",
            found__contains=str(document.pk),
        ).values_list("result_id", flat=True)
    )

    result.issues.all().delete()
    clear_cross_checks(document)
    for issue in validate_result(result):
        ValidationIssue.objects.create(document=document, result=result, **issue)

    result.review_status = ExtractionResult.ReviewStatus.OK
    result.save(update_fields=["review_status", "updated_at"])
    refresh_review_state(result)

    cross_verify_document(document)
    for other in (
        ExtractionResult.objects.filter(pk__in=affected_ids)
        .exclude(pk=result.pk)
        .select_related("document")
    ):
        refresh_review_state(other)
        update_document_status(other.document)

    result.refresh_from_db()
    update_document_status(document)


@transaction.atomic
def apply_correction(
    result: ExtractionResult, data: dict, note: str = ""
) -> list[CorrectionLog]:
    """Apply a partial update. Only fields present in data change; every change is logged."""
    logs: list[CorrectionLog] = []

    for name in SCALAR_FIELDS:
        if name not in data:
            continue

        old, new = getattr(result, name), _normalise(name, data[name])
        if old == new or (
            isinstance(old, Decimal)
            and isinstance(new, Decimal)
            and old == new
        ):
            continue

        setattr(result, name, new)
        logs.append(
            CorrectionLog(
                result=result,
                field=name,
                old_value=_text(old),
                new_value=_text(new),
                note=note,
            )
        )

    if "line_items" in data:
        before_items = list(result.line_items.all())
        before = _lines_snapshot(before_items)
        result.line_items.all().delete()

        LineItem.objects.bulk_create(
            [
                LineItem(
                    result=result,
                    position=index,
                    description=_normalise("description", item.get("description")),
                    quantity=item.get("quantity"),
                    unit_price=item.get("unit_price"),
                    amount=item.get("amount"),
                )
                for index, item in enumerate(data["line_items"], start=1)
            ]
        )

        after = _lines_snapshot(result.line_items.all())
        if before != after:
            logs.append(
                CorrectionLog(
                    result=result,
                    field="line_items",
                    old_value=before,
                    new_value=after,
                    note=note,
                )
            )

    result.dedupe_key = make_dedupe_key(
        result.supplier_name, result.invoice_number
    )
    result.save()

    CorrectionLog.objects.bulk_create(logs)
    revalidate(result)
    transaction.on_commit(lambda: safe_index_result(result))
    return logs


@transaction.atomic
def create_manual_result(document: Document, data: dict) -> ExtractionResult:
    """Enter an invoice by hand (for example when extraction found nothing)."""
    result = ExtractionResult.objects.create(
        document=document,
        method=ExtractionResult.Method.MANUAL,
        review_status=ExtractionResult.ReviewStatus.OK,
    )
    apply_correction(result, data, note="Entered manually")

    document.issues.filter(
        result__isnull=True,
        code="NO_INVOICE_FOUND",
    ).update(resolved=True)

    update_document_status(document)
    result.refresh_from_db()
    return result


@transaction.atomic
def approve_result(result: ExtractionResult) -> ExtractionResult:
    """A reviewer confirms the values as they are: open issues are marked resolved."""
    result.issues.filter(resolved=False).update(resolved=True)
    result.review_status = ExtractionResult.ReviewStatus.REVIEWED
    result.save(update_fields=["review_status", "updated_at"])
    update_document_status(result.document)
    return result
