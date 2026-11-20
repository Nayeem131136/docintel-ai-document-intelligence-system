"""The in-memory shape of one extracted invoice before it is saved to the database."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class Note:
    """Something worth telling the reviewer about the extraction itself."""

    code: str
    message: str
    severity: str = "warning"
    field: str = ""


@dataclass
class Draft:
    invoice_number: str | None = None
    invoice_date: date | None = None
    supplier_name: str | None = None
    customer_name: str | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    line_items: list[dict] = field(default_factory=list)   # description, quantity, unit_price, amount
    confidence: dict = field(default_factory=dict)
    method: str = "rules"                                    # llm | rules | table
    model_name: str = ""
    notes: list[Note] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    page_start: int | None = None
    page_end: int | None = None

    FIELDS = ("invoice_number", "invoice_date", "supplier_name", "customer_name",
              "currency", "subtotal", "tax", "total")
