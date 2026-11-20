"""Split a multi-page document into per-invoice segments.

A 1000-page PDF can hold hundreds of invoices. We only start a new segment when a
page shows an invoice number that differs from the current segment's number; pages
without a number are treated as continuation pages. This is deliberately
conservative: it never splits one invoice into two because page 2 lacks a header.
"""
from dataclasses import dataclass, field

from .numbers import alnum
from .rules import _find_invoice_number


@dataclass
class Segment:
    page_start: int
    page_end: int
    texts: list[tuple[int, str]] = field(default_factory=list)   # (page_number, text)
    number: str | None = None

    def text(self) -> str:
        return "\n\n".join(f"--- page {n} ---\n{t}" for n, t in self.texts if t.strip())


def segment_pages(pages: list[tuple[int, str]]) -> list[Segment]:
    """``pages`` is [(page_number, text)] in order. Pages with no text are skipped."""
    segments: list[Segment] = []
    current: Segment | None = None
    for number, text in pages:
        if not text.strip():
            if current:
                current.page_end = number
            continue
        found = _find_invoice_number(text)
        starts_new = (
            current is None
            or (found is not None and current.number is not None and alnum(found) != alnum(current.number))
        )
        if starts_new:
            current = Segment(page_start=number, page_end=number, number=found)
            segments.append(current)
        else:
            current.page_end = number
            if current.number is None:
                current.number = found
        current.texts.append((number, text))
    return segments
