"""Shared types and helpers for the extractors."""
from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass
class PageResult:
    """Text (and optional table) extracted from one PDF page, image, or sheet."""

    page_number: int                       # 1-based
    text: str = ""
    source: str = "digital"                # digital | ocr | spreadsheet
    ocr_confidence: Optional[float] = None
    sheet_name: str = ""
    table: Optional[dict] = None           # {"rows": [[...]], "truncated": bool} for spreadsheets
    error: str = ""                        # non-empty => this page failed
    warning: str = ""                      # non-fatal note (e.g. truncated rows)

    @property
    def has_error(self) -> bool:
        return bool(self.error)


@dataclass
class Extraction:
    """A lazily-evaluated extraction: ``total`` pages, produced one at a time.

    Streaming keeps memory flat for ~1000-page PDFs and lets the pipeline report progress.
    """

    total: int
    pages: Iterator[PageResult] = field(repr=False)


def clean_text(value: str) -> str:
    """Remove characters PostgreSQL cannot store (NUL) and normalise line endings."""
    return value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
