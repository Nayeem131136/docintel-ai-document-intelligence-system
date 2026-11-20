"""Excel / CSV 'invoice register' mapping: one row per invoice, no LLM needed.

If a sheet has a header row with an invoice-number column and a total column, every
following row becomes one invoice. Any other sheet is treated like a normal document
(its text goes through the LLM / rules extractor).
"""
import re
from decimal import Decimal

from .draft import Draft, Note
from .numbers import clean_name, is_ambiguous_date, parse_amount, parse_date

HEADER_SYNONYMS = {
    "invoice_number": {"invoice no", "invoice number", "invoice", "inv no", "inv number", "invoice id",
                       "bill no", "invoice num", "invoice nr"},
    "invoice_date": {"invoice date", "date", "issue date", "bill date", "date of issue"},
    "supplier_name": {"supplier", "supplier name", "vendor", "vendor name", "seller", "from"},
    "customer_name": {"customer", "customer name", "client", "client name", "buyer", "bill to", "sold to"},
    "subtotal": {"subtotal", "sub total", "net", "net amount", "amount before tax"},
    "tax": {"tax", "vat", "gst", "tax amount", "vat amount"},
    "total": {"total", "grand total", "total amount", "amount", "invoice total", "gross", "amount due"},
    "currency": {"currency", "ccy"},
}
SEARCH_ROWS = 10   # the header must be within the first rows


def _norm_header(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def find_register_header(rows: list[list]) -> tuple[int, dict[int, str]] | None:
    """Return (header_row_index, {column_index: field}) or None if this is not a register."""
    for row_index, row in enumerate(rows[:SEARCH_ROWS]):
        mapping: dict[int, str] = {}
        taken: set[str] = set()
        for column, cell in enumerate(row):
            header = _norm_header(cell)
            for name, synonyms in HEADER_SYNONYMS.items():
                if header in synonyms and name not in taken:
                    mapping[column] = name
                    taken.add(name)
                    break
        if "invoice_number" in taken and "total" in taken:
            return row_index, mapping
    return None


def drafts_from_register(rows: list[list], page_number: int) -> list[Draft] | None:
    header = find_register_header(rows)
    if header is None:
        return None
    header_index, mapping = header
    drafts: list[Draft] = []
    for offset, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        values = {name: (row[column] if column < len(row) else None) for column, name in mapping.items()}
        if not any(v is not None for v in values.values()):
            continue
        draft = Draft(method="table", page_start=page_number, page_end=page_number)
        draft.raw = {"sheet_row": offset}
        number = values.get("invoice_number")
        draft.invoice_number = clean_name(number) if number is not None else None
        draft.supplier_name = clean_name(values.get("supplier_name"))
        draft.customer_name = clean_name(values.get("customer_name"))
        currency = clean_name(values.get("currency"))
        draft.currency = currency.upper() if currency and re.fullmatch(r"[A-Za-z]{3}", currency) else None

        raw_date = values.get("invoice_date")
        draft.invoice_date = parse_date(raw_date)
        if raw_date is not None and draft.invoice_date is None:
            code = "AMBIGUOUS_DATE" if is_ambiguous_date(raw_date) else "INVALID_DATE"
            draft.notes.append(Note(code, f"Row {offset}: date '{raw_date}' could not be read unambiguously; left empty.",
                                    "warning", "invoice_date"))
        for name in ("subtotal", "tax", "total"):
            raw = values.get(name)
            amount = parse_amount(raw)
            setattr(draft, name, amount)
            if raw is not None and amount is None:
                draft.notes.append(Note("INVALID_NUMBER", f"Row {offset}: {name} '{raw}' is not a number; left empty.",
                                        "warning", name))
        drafts.append(draft)
    return drafts
