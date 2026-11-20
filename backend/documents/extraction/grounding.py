"""Anti-hallucination: keep an extracted value only if it can be found in the source text.

The LLM is asked to answer null for anything it cannot see, but models sometimes
guess anyway. This module is the second line of defence: a value that does not
appear in the document is dropped (set to None) and reported to the reviewer.
"""
import re
from decimal import Decimal

from .draft import Draft, Note
from .numbers import alnum, date_interpretations, numbers_in_text

CURRENCY_SYMBOLS = {
    "USD": ("$", "us$"), "EUR": ("€",), "GBP": ("£",), "INR": ("₹",), "BDT": ("৳", "tk"),
    "JPY": ("¥",), "CNY": ("¥", "rmb"),
}
_WORD = re.compile(r"[0-9a-z]+")


def text_grounded(value: str, source: str, *, min_ratio: float = 1.0) -> bool:
    """True when ``value`` appears in ``source`` ignoring case, spacing and punctuation."""
    needle = alnum(value)
    if not needle:
        return False
    if needle in alnum(source):
        return True
    words = [w for w in _WORD.findall(value.casefold()) if len(w) >= 2]
    if not words:
        return False
    source_words = set(_WORD.findall(source.casefold()))
    return sum(w in source_words for w in words) / len(words) >= min_ratio


def currency_grounded(code: str, source: str) -> bool:
    upper, lower = source.upper(), source.casefold()
    if re.search(rf"\b{re.escape(code.upper())}\b", upper):
        return True
    return any(symbol in lower for symbol in CURRENCY_SYMBOLS.get(code.upper(), ()))


def ground_draft(draft: Draft, source: str) -> Draft:
    """Drop every value that is not present in ``source``; record what was dropped."""
    numbers = numbers_in_text(source)
    dates = date_interpretations(source)
    dropped: dict[str, object] = {}

    def drop(name: str, value, why: str = "was not found in the document text"):
        dropped[name] = str(value)
        draft.notes.append(Note("UNGROUNDED_VALUE", f"{name.replace('_', ' ')} '{value}' {why}; left empty.",
                                "warning", name))
        draft.confidence.pop(name, None)

    if draft.invoice_number and not text_grounded(draft.invoice_number, source):
        drop("invoice_number", draft.invoice_number)
        draft.invoice_number = None
    for name in ("supplier_name", "customer_name"):
        value = getattr(draft, name)
        if value and not text_grounded(value, source, min_ratio=0.8):
            drop(name, value)
            setattr(draft, name, None)
    if draft.invoice_date and draft.invoice_date not in dates:
        drop("invoice_date", draft.invoice_date)
        draft.invoice_date = None
    if draft.currency and not currency_grounded(draft.currency, source):
        drop("currency", draft.currency)
        draft.currency = None
    for name in ("subtotal", "tax", "total"):
        value = getattr(draft, name)
        if value is not None and abs(value) not in numbers:
            drop(name, value)
            setattr(draft, name, None)

    kept_items = []
    for index, item in enumerate(draft.line_items, start=1):
        for name in ("quantity", "unit_price", "amount"):
            value = item.get(name)
            if isinstance(value, Decimal) and abs(value) not in numbers:
                dropped[f"line_items[{index}].{name}"] = str(value)
                draft.notes.append(Note("UNGROUNDED_VALUE",
                                        f"line {index} {name.replace('_', ' ')} '{value}' was not found in the "
                                        "document text; left empty.", "warning", f"line_items[{index}]"))
                item[name] = None
        description = item.get("description")
        if description and not text_grounded(description, source, min_ratio=0.7):
            dropped[f"line_items[{index}].description"] = description
            draft.notes.append(Note("UNGROUNDED_VALUE", f"line {index} description was not found in the "
                                    "document text; left empty.", "warning", f"line_items[{index}]"))
            item["description"] = None
        if any(item.get(k) is not None for k in ("description", "quantity", "unit_price", "amount")):
            kept_items.append(item)
    draft.line_items = kept_items

    if dropped:
        draft.raw["dropped_ungrounded"] = dropped
    return draft
