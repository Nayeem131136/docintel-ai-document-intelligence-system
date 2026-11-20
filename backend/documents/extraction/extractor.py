
"""Extract one invoice from one segment of text: LLM first, rules as the fallback."""
import logging
from datetime import date
from decimal import Decimal

from django.conf import settings

from .draft import Draft, Note
from .grounding import ground_draft
from .llm import LLMError
from .numbers import clean_name, is_ambiguous_date, parse_amount, parse_date
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from .rules import extract_with_rules

logger = logging.getLogger(__name__)


def max_chars() -> int:
    return int(getattr(settings, "EXTRACTION_MAX_CHARS", 30000))


def _clamp(value) -> float | None:
    try:
        return round(min(1.0, max(0.0, float(value))), 3)
    except (TypeError, ValueError):
        return None


def draft_from_llm_json(data: dict, model_name: str) -> Draft:
    """Convert (and strictly validate) the model's JSON. Unknown keys are ignored."""
    draft = Draft(method="llm", model_name=model_name)
    draft.raw = {"prompt_version": PROMPT_VERSION, "llm_output": data}

    number = data.get("invoice_number")
    draft.invoice_number = clean_name(number) if isinstance(number, (str, int)) else None

    for name in ("supplier_name", "customer_name"):
        value = data.get(name)
        setattr(draft, name, clean_name(value) if isinstance(value, str) else None)

    currency = data.get("currency")
    draft.currency = (
        currency.strip().upper()
        if isinstance(currency, str) and len(currency.strip()) == 3
        else None
    )

    raw_date = data.get("invoice_date")
    draft.invoice_date = parse_date(raw_date) if isinstance(raw_date, (str, date)) else None

    if raw_date and draft.invoice_date is None:
        code = "AMBIGUOUS_DATE" if is_ambiguous_date(raw_date) else "INVALID_DATE"
        draft.notes.append(
            Note(
                code,
                f"Date '{raw_date}' could not be read unambiguously; left empty.",
                "warning",
                "invoice_date",
            )
        )

    for name in ("subtotal", "discount", "tax", "total"):
        value = data.get(name)
        amount = parse_amount(value)

        # A discount reduces the payable amount, so store it as negative.
        if name == "discount" and amount is not None:
            amount = -abs(amount)

        setattr(draft, name, amount)

        if value is not None and amount is None:
            draft.notes.append(
                Note(
                    "INVALID_NUMBER",
                    f"{name} '{value}' is not a number; left empty.",
                    "warning",
                    name,
                )
            )

    items = data.get("line_items")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue

        description = item.get("description")
        draft.line_items.append(
            {
                "description": clean_name(description) if isinstance(description, str) else None,
                "quantity": parse_amount(item.get("quantity")),
                "unit_price": parse_amount(item.get("unit_price")),
                "amount": parse_amount(item.get("amount")),
            }
        )

    confidence = data.get("confidence")
    if isinstance(confidence, dict):
        for name in Draft.FIELDS:
            value = _clamp(confidence.get(name))
            if value is not None and getattr(draft, name) is not None:
                draft.confidence[name] = value

    return draft


def extract_segment(text: str, llm, *, page_start: int, page_end: int) -> Draft:
    """Return a grounded Draft. ``llm`` may be None (rules only)."""
    notes: list[Note] = []
    source = text

    if len(text) > max_chars():
        text = text[: max_chars()]
        notes.append(
            Note(
                "TEXT_TRUNCATED",
                f"The invoice text was longer than {max_chars()} characters; "
                "only the beginning was analysed.",
                "warning",
            )
        )

    draft: Draft | None = None

    if llm is not None:
        try:
            data = llm.complete_json(SYSTEM_PROMPT, build_user_prompt(text))
            draft = draft_from_llm_json(data, getattr(llm, "model", ""))
        except LLMError as exc:
            logger.warning("LLM extraction failed, using rules: %s", exc)
            notes.append(
                Note(
                    "EXTRACTION_FALLBACK",
                    f"AI extraction failed ({exc}); rule-based extraction was used instead.",
                    "warning",
                )
            )

    if draft is None:
        draft = extract_with_rules(text)
        if llm is None:
            notes.append(
                Note(
                    "EXTRACTION_FALLBACK",
                    "No LLM is configured; rule-based extraction was used. Check every field.",
                    "info",
                )
            )

    draft.page_start, draft.page_end = page_start, page_end
    draft.notes.extend(notes)

    return ground_draft(draft, source)
