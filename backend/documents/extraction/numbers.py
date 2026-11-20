"""Parsing and normalising money amounts, dates and strings found in invoices.

Everything here is conservative: when a value is ambiguous it returns ``None``
instead of guessing (a guessed value would be an invented value).
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

# ----------------------------------------------------------------------------- amounts
_CURRENCY_NOISE = re.compile(r"[^\d.,\-()+\s]")
_THOUSANDS_COMMA = re.compile(r"^\d{1,3}(,\d{3})+$")
_THOUSANDS_DOT = re.compile(r"^\d{1,3}(\.\d{3})+$")
# "1.150.00": dots used as thousands separators with a 1-2 digit tail. Real-world cause:
# OCR reading the decimal point of "1,150.00" wrongly. Interpreted as 1150.00.
_DOTS_THEN_DECIMAL = re.compile(r"^\d{1,3}(\.\d{3})+\.\d{1,2}$")
_COMMAS_THEN_DECIMAL = re.compile(r"^\d{1,3}(,\d{3})+,\d{1,2}$")


def parse_amount(value) -> Decimal | None:
    """Parse '1,150.00', '1.150,00', '$ 99', '(100.00)', 1150.5 ... into a Decimal, else None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value)) if value == value and value not in (float("inf"), float("-inf")) else None

    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")") or text.lstrip().startswith("-")
    text = _CURRENCY_NOISE.sub("", text)
    text = re.sub(r"[()+\-\s]", "", text)
    if not text or not re.search(r"\d", text):
        return None

    if "." in text and "," in text:
        decimal_sep = "." if text.rfind(".") > text.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        text = text.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in text:
        if _THOUSANDS_COMMA.match(text):
            text = text.replace(",", "")
        elif _COMMAS_THEN_DECIMAL.match(text):
            head, tail = text.rsplit(",", 1)
            text = head.replace(",", "") + "." + tail
        elif text.count(",") == 1 and re.match(r"^\d+,\d{1,2}$", text):
            text = text.replace(",", ".")          # decimal comma: 100,50
        else:
            return None
    elif "." in text:
        if text.count(".") > 1:
            if _THOUSANDS_DOT.match(text):
                text = text.replace(".", "")
            elif _DOTS_THEN_DECIMAL.match(text):
                head, tail = text.rsplit(".", 1)
                text = head.replace(".", "") + "." + tail
            else:
                return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return -number if negative else number


_NUMBER_TOKEN = re.compile(r"\d[\d.,]*")


def numbers_in_text(text: str) -> set[Decimal]:
    """Every numeric value appearing in text, including OCR-spaced thousands separators."""
    found: set[Decimal] = set()

    # Repair OCR spacing: "1, 150.00" -> "1,150.00"
    text = re.sub(r"(?<=\d),\s+(?=\d)", "", text)

    for token in _NUMBER_TOKEN.findall(text):
        token = token.rstrip(".,")
        number = parse_amount(token)
        if number is not None:
            found.add(abs(number))
    return found


def to_money(value, places: int = 2) -> Decimal | None:
    number = parse_amount(value)
    if number is None:
        return None
    return number.quantize(Decimal(1).scaleb(-places))


# ----------------------------------------------------------------------------- dates
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"

_YMD = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_DMY = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b")
_D_MON_Y = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s\-]+{_MONTH_RE}[,\s\-]+(\d{{2,4}})\b", re.I)
_MON_D_Y = re.compile(rf"\b{_MONTH_RE}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{2,4}})\b", re.I)


def _year(value: str) -> int:
    year = int(value)
    if year < 100:
        year += 2000 if year < 70 else 1900
    return year


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def date_interpretations(text: str) -> set[date]:
    """All valid dates that ``text`` can be read as (both D/M/Y and M/D/Y when ambiguous)."""
    results: set[date] = set()
    for y, m, d in _YMD.findall(text):
        found = _safe_date(int(y), int(m), int(d))
        if found:
            results.add(found)
    for a, b, y in _DMY.findall(text):
        for day, month in ((int(a), int(b)), (int(b), int(a))):
            found = _safe_date(_year(y), month, day)
            if found:
                results.add(found)
    for d, mon, y in _D_MON_Y.findall(text):
        found = _safe_date(_year(y), _MONTHS[mon.lower()[:3]], int(d))
        if found:
            results.add(found)
    for mon, d, y in _MON_D_Y.findall(text):
        found = _safe_date(_year(y), _MONTHS[mon.lower()[:3]], int(d))
        if found:
            results.add(found)
    return results


def parse_date(value) -> date | None:
    """A single unambiguous date, or None (ambiguous 03/04/2026 is NOT guessed)."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    options = date_interpretations(str(value))
    return next(iter(options)) if len(options) == 1 else None


def is_ambiguous_date(value) -> bool:
    return value is not None and not isinstance(value, date) and len(date_interpretations(str(value))) > 1


# ----------------------------------------------------------------------------- strings
def alnum(text: str) -> str:
    """Lower-case letters and digits only: for comparing names and ids across formatting."""
    return re.sub(r"[^0-9a-z]", "", (text or "").casefold())


def clean_name(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def make_dedupe_key(supplier: str | None, invoice_number: str | None) -> str:
    """Key identifying 'the same invoice': normalised supplier + invoice number."""
    if not invoice_number:
        return ""
    return f"{alnum(supplier) or '?'}|{alnum(invoice_number)}"[:400]
