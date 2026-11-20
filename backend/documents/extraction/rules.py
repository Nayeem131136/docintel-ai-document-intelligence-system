"""Rule-based (regex) extractor: the fallback when no LLM is available or the LLM fails.

It only returns what is explicitly labelled in the text. Anything it cannot find
stays None - for example the supplier is never "guessed" from the first line.
"""
import re
from decimal import Decimal

from .draft import Draft, Note
from .numbers import clean_name, is_ambiguous_date, parse_amount, parse_date, date_interpretations

CURRENCY_CODES = ("USD", "EUR", "GBP", "BDT", "INR", "AUD", "CAD", "JPY", "CNY", "SGD", "AED", "SAR",
                  "MYR", "CHF", "PKR", "NZD", "HKD", "THB")
_SYMBOL_TO_CODE = {"€": "EUR", "£": "GBP", "₹": "INR", "৳": "BDT"}   # "$" and "¥" are ambiguous: not guessed

INVOICE_NUMBER = re.compile(
    r"\b(?:tax\s+)?(?:invoice|inv|receipt|bill)\s*(?:no\.?|number|num\.?|#|id)?\s*[:#\-]?\s*"
    r"([A-Z0-9][A-Z0-9\-/_.]{1,40})", re.I)
DATE_LABEL = re.compile(
    r"(?:invoice\s*date|date\s*of\s*issue|issue\s*date|bill\s*date|date)\s*[:\-]?\s*(.{6,30})", re.I)
SUPPLIER_LABEL = re.compile(r"^\s*(?:supplier|vendor|seller|issued\s*by|from)(?:\s*name)?\s*[:\-]\s*(.+)$", re.I)
CUSTOMER_LABEL = re.compile(
    r"^\s*(?:bill(?:ed)?\s*to|customer|client|sold\s*to|buyer|ship\s*to)(?:\s*name)?\s*[:\-]?\s*(.+)$", re.I)

SUBTOTAL_LABEL = re.compile(r"\b(?:sub\s*-?\s*total|net\s*amount|amount\s*before\s*tax|total\s*before\s*tax)\b", re.I)
TAX_LABEL = re.compile(r"\b(?:vat|gst|sales\s*tax|tax)\b", re.I)
TOTAL_LABEL = re.compile(
    r"\b(?:grand\s*total|total\s*(?:due|amount|payable|invoice)?|amount\s*(?:due|payable)|balance\s*due)\b", re.I)
_PERCENT = re.compile(r"\d+(?:[.,]\d+)?\s*%")
_NUMBER = re.compile(r"-?\(?\d[\d.,]*\)?")
_ROW_SPLIT = re.compile(r"\s{2,}|\s\|\s|\t")
_SKIP_ITEM_WORDS = re.compile(r"\b(?:sub\s*-?\s*total|total|tax|vat|gst|discount|balance|amount\s*due|shipping)\b", re.I)


def _last_amount(line: str) -> Decimal | None:
    line = _PERCENT.sub(" ", line)
    # Repair OCR spacing inside thousands separators: "1, 150.00" -> "1,150.00"
    line = re.sub(r"(?<=\d),\s+(?=\d)", "", line)
    for token in reversed(_NUMBER.findall(line)):
        amount = parse_amount(token.rstrip(".,"))
        if amount is not None:
            return amount
    return None


def _find_invoice_number(text: str) -> str | None:
    for match in INVOICE_NUMBER.finditer(text):
        value = match.group(1).rstrip(".-/_")
        if re.search(r"\d", value):
            return value
    return None


def _find_date(text: str, draft: Draft):
    for match in DATE_LABEL.finditer(text):
        candidate = match.group(1)
        options = date_interpretations(candidate)
        if len(options) == 1:
            return next(iter(options))
        if len(options) > 1:
            draft.notes.append(Note("AMBIGUOUS_DATE", f"'{candidate.strip()}' can be read as more than one date "
                                    "(day/month order is unclear); left empty.", "warning", "invoice_date"))
            return None
    return None


def _find_currency(text: str) -> str | None:
    match = re.search(r"\b(" + "|".join(CURRENCY_CODES) + r")\b", text.upper())
    if match:
        return match.group(1)
    for symbol, code in _SYMBOL_TO_CODE.items():
        if symbol in text:
            return code
    return None


def parse_line_item(line: str) -> dict | None:
    """'Widget   2   50.00   100.00' (or ' | ' separated) -> a line item, else None."""
    if _SKIP_ITEM_WORDS.search(line):
        return None
    parts = [p.strip() for p in _ROW_SPLIT.split(line.strip()) if p.strip()]
    if len(parts) < 4:
        return None
    quantity, unit_price, amount = (parse_amount(p) for p in parts[-3:])
    if quantity is None or unit_price is None or amount is None:
        return None
    description = " ".join(parts[:-3])
    if not re.search(r"[A-Za-z]", description):
        return None
    return {"description": clean_name(description), "quantity": quantity, "unit_price": unit_price, "amount": amount}


def extract_with_rules(text: str) -> Draft:
    draft = Draft(method="rules")
    draft.invoice_number = _find_invoice_number(text)
    draft.invoice_date = _find_date(text, draft)
    draft.currency = _find_currency(text)

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if draft.supplier_name is None and (m := SUPPLIER_LABEL.match(stripped)):
            draft.supplier_name = clean_name(re.split(r"\s{2,}|\s\|\s", m.group(1))[0])
        elif draft.customer_name is None and (m := CUSTOMER_LABEL.match(stripped)):
            draft.customer_name = clean_name(re.split(r"\s{2,}|\s\|\s", m.group(1))[0])

        item = parse_line_item(stripped)
        if item:
            draft.line_items.append(item)
            continue
        amount = _last_amount(stripped)
        if amount is None:
            continue
        if SUBTOTAL_LABEL.search(stripped):
            draft.subtotal = amount
        elif TOTAL_LABEL.search(stripped):
            draft.total = amount                     # the last "total" line wins (grand total)
        elif TAX_LABEL.search(stripped):
            draft.tax = amount
    return draft
