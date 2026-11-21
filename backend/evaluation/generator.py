"""Synthetic invoice dataset with exact ground truth.

Run through ``python manage.py generate_eval_dataset``. The data is seeded, so the same seed always produces
the same files. Documents are rendered as digital PDFs, scanned PDFs, photos, TIFFs, spreadsheets and CSVs,
with injected problems (wrong totals, missing dates, duplicates, PDF/Excel mismatches) whose expected
validation outcome is recorded in ``ground_truth.json``.
"""
import csv
import io
import json
import random
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pymupdf
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .catalog import CUSTOMERS, ITEMS, STREETS, SUPPLIERS

CENT = Decimal("0.01")
SCALE = 150 / 72                       # points -> pixels at 150 dpi
FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf",
              "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]
BOLD_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
SYMBOLS = {"EUR": "€", "GBP": "£"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def q2(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Item:
    key: str
    description: str
    qty: int
    unit: Decimal

    @property
    def amount(self) -> Decimal:
        return q2(self.qty * self.unit)


@dataclass
class Invoice:
    number: str
    date: date | None
    supplier: str
    customer: str
    currency: str
    items: list[Item]
    tax_rate: int
    money_style: str = "plain"           # plain 1,234.50 | eu 1.234,50 | sym €1,234.50
    date_style: int = 0
    total_delta: Decimal = Decimal("0")  # injected error: printed total differs from subtotal + tax
    page_items: int = 14
    discount_pct: int = 0                # printed as a negative "Discount" line (0 = no discount line)

    @property
    def subtotal(self) -> Decimal:
        return q2(sum((i.amount for i in self.items), Decimal("0")))

    @property
    def discount(self) -> Decimal | None:
        return -q2(self.subtotal * self.discount_pct / 100) if self.discount_pct else None

    @property
    def tax(self) -> Decimal:
        return q2(self.subtotal * self.tax_rate / 100)

    @property
    def total(self) -> Decimal:
        return q2(self.subtotal + (self.discount or 0) + self.tax + self.total_delta)

    def truth(self) -> dict:
        return {
            "invoice_number": self.number, "invoice_date": self.date.isoformat() if self.date else None,
            "supplier_name": self.supplier, "customer_name": self.customer, "currency": self.currency,
            "subtotal": str(self.subtotal), "discount": str(self.discount) if self.discount is not None else None,
            "tax": str(self.tax), "total": str(self.total),
            "item_count": len(self.items), "items": [i.key for i in self.items if i.key],
        }


# --------------------------------------------------------------------------- formatting
def fmt_money(value: Decimal, style: str, currency: str) -> str:
    if value < 0:
        return "-" + fmt_money(-value, style, currency)
    text = f"{value:,.2f}"
    if style == "eu":
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    if style == "sym" and currency in SYMBOLS:
        return f"{SYMBOLS[currency]}{text}"
    return text


def fmt_date(d: date, style: int) -> str:
    if style == 0:
        return d.isoformat()
    if style == 1:
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    if style == 2:
        return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"
    return f"{d.day:02d}-{MONTHS[d.month - 1][:3]}-{d.year}"


# --------------------------------------------------------------------------- layouts (lists of draw operations)
Op = tuple[float, float, str, float, bool]          # x, y, text, font size (pt), bold


def _chunks(items: list[Item], size: int) -> list[list[Item]]:
    return [items[i:i + size] for i in range(0, len(items), size)] or [[]]


def layout_a(inv: Invoice) -> list[list[Op]]:
    """Plain header block, ruled table, totals on the right."""
    pages, parts = [], _chunks(inv.items, inv.page_items)
    m = lambda v: fmt_money(v, inv.money_style, inv.currency)
    for index, part in enumerate(parts):
        ops: list[Op] = []
        y = 60
        header = [f"Supplier: {inv.supplier}", f"Invoice No: {inv.number}"]
        if inv.date:
            header.append(f"Invoice Date: {fmt_date(inv.date, inv.date_style)}")
        header += [f"Bill To: {inv.customer}", f"Currency: {inv.currency}"]
        if len(parts) > 1:
            header.append(f"Page {index + 1} of {len(parts)}")
        for line in header:
            ops.append((72, y, line, 11, False))
            y += 18
        y += 10
        for x, cell in zip((72, 300, 380, 470), ("Description", "Qty", "Unit", "Amount")):
            ops.append((x, y, cell, 11, True))
        y += 18
        for item in part:
            for x, cell in zip((72, 300, 380, 470), (item.description, str(item.qty), m(item.unit), m(item.amount))):
                ops.append((x, y, cell, 11, False))
            y += 18
        if index == len(parts) - 1:
            rows = [("Subtotal", inv.subtotal)]
            if inv.discount is not None:
                rows.append((f"Discount {inv.discount_pct}%", inv.discount))
            rows += [(f"Tax {inv.tax_rate}%", inv.tax), ("Total", inv.total)]
            for label, value in rows:
                ops.append((72, y, label, 11, label == "Total"))
                ops.append((470, y, m(value), 11, label == "Total"))
                y += 18
        pages.append(ops)
    return pages


def layout_b(inv: Invoice) -> list[list[Op]]:
    """Letterhead style: supplier name big at the top left, INVOICE title and numbers at the right."""
    pages, parts = [], _chunks(inv.items, inv.page_items)
    m = lambda v: fmt_money(v, inv.money_style, inv.currency)
    for index, part in enumerate(parts):
        ops: list[Op] = [(60, 60, inv.supplier.upper(), 17, True), (60, 78, STREETS[len(inv.supplier) % len(STREETS)], 9, False),
                         (390, 60, "INVOICE", 20, True), (390, 90, f"Invoice # {inv.number}", 11, False)]
        if inv.date:
            ops.append((390, 106, f"Date: {fmt_date(inv.date, inv.date_style)}", 11, False))
        if len(parts) > 1:
            ops.append((390, 122, f"Page {index + 1} of {len(parts)}", 9, False))
        ops += [(60, 150, "Billed to:", 10, True), (60, 166, inv.customer, 11, False)]
        y = 210
        for x, cell in zip((60, 300, 380, 480), ("Item", "Quantity", "Price", "Total")):
            ops.append((x, y, cell, 11, True))
        y += 20
        for item in part:
            for x, cell in zip((60, 300, 380, 480), (item.description, str(item.qty), m(item.unit), m(item.amount))):
                ops.append((x, y, cell, 11, False))
            y += 18
        if index == len(parts) - 1:
            y += 8
            rows = [("Subtotal", inv.subtotal, False)]
            if inv.discount is not None:
                rows.append((f"Discount ({inv.discount_pct}%)", inv.discount, False))
            rows += [(f"VAT ({inv.tax_rate}%)", inv.tax, False), ("Grand Total", inv.total, True)]
            for label, value, bold in rows:
                ops.append((330, y, label, 11, bold))
                ops.append((480, y, m(value), 11, bold))
                y += 18
            ops.append((60, y + 30, f"All amounts in {inv.currency}", 9, False))
        pages.append(ops)
    return pages


def layout_c(inv: Invoice) -> list[list[Op]]:
    """Compact tax-invoice style with different wording."""
    pages, parts = [], _chunks(inv.items, inv.page_items)
    m = lambda v: fmt_money(v, inv.money_style, inv.currency)
    for index, part in enumerate(parts):
        ops: list[Op] = [(200, 55, "TAX INVOICE", 16, True), (72, 90, f"Inv. No.: {inv.number}", 11, False)]
        y = 108
        if inv.date:
            ops.append((72, y, f"Issued: {fmt_date(inv.date, inv.date_style)}", 11, False))
            y += 18
        ops += [(72, y, f"From: {inv.supplier}", 11, False), (72, y + 18, f"To: {inv.customer}", 11, False),
                (72, y + 36, f"Currency: {inv.currency}", 11, False)]
        y += 70
        for x, cell in zip((72, 310, 370, 470), ("Details", "Qty", "Rate", "Line total")):
            ops.append((x, y, cell, 10, True))
        y += 18
        for item in part:
            for x, cell in zip((72, 310, 370, 470), (item.description, str(item.qty), m(item.unit), m(item.amount))):
                ops.append((x, y, cell, 10, False))
            y += 16
        if index == len(parts) - 1:
            y += 8
            rows = [("Sub-total", inv.subtotal, False)]
            if inv.discount is not None:
                rows.append((f"Less: discount {inv.discount_pct}%", inv.discount, False))
            rows += [(f"Tax @ {inv.tax_rate}%", inv.tax, False), ("Amount due", inv.total, True)]
            for label, value, bold in rows:
                ops.append((330, y, label, 10, bold))
                ops.append((470, y, m(value), 10, bold))
                y += 16
        pages.append(ops)
    return pages


LAYOUTS = {"A": layout_a, "B": layout_b, "C": layout_c}


# --------------------------------------------------------------------------- renderers
def _unicode_font(bold: bool) -> str | None:
    for candidate in (BOLD_PATHS if bold else FONT_PATHS):
        if Path(candidate).exists():
            return candidate
    return None


def write_pdf(path: Path, pages: list[list[Op]]) -> None:
    """Base-14 fonts cannot draw the euro / pound signs, so those lines use a Unicode TTF when one exists
    (otherwise the symbol is replaced by the currency code)."""
    doc = pymupdf.open()
    for ops in pages:
        page = doc.new_page()
        for x, y, text, size, bold in ops:
            if any(symbol in text for symbol in SYMBOLS.values()):
                font_file = _unicode_font(bold)
                if font_file:
                    page.insert_font(fontname="uni-b" if bold else "uni", fontfile=font_file)
                    page.insert_text((x, y), text, fontsize=size, fontname="uni-b" if bold else "uni")
                    continue
                for code, symbol in SYMBOLS.items():
                    text = text.replace(symbol, f"{code} ")
            page.insert_text((x, y), text, fontsize=size, fontname="hebo" if bold else "helv")
    doc.save(path)
    doc.close()


def _font(size: float, bold: bool) -> ImageFont.ImageFont:
    for candidate in (BOLD_PATHS if bold else FONT_PATHS):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, int(round(size * SCALE)))
    return ImageFont.load_default(size=int(round(size * SCALE)))


def render_image(ops: list[Op]) -> Image.Image:
    image = Image.new("RGB", (int(595 * SCALE), int(842 * SCALE)), "white")
    draw = ImageDraw.Draw(image)
    for x, y, text, size, bold in ops:
        draw.text((x * SCALE, (y - size) * SCALE), text, font=_font(size, bold), fill=(20, 20, 20))
    return image


def degrade(image: Image.Image, rng: random.Random, strength: str) -> Image.Image:
    """Make a clean render look scanned ('scan') or photographed ('photo')."""
    angle = rng.uniform(-1.0, 1.0) if strength == "scan" else rng.uniform(-2.5, 2.5)
    image = image.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))
    image = image.filter(ImageFilter.GaussianBlur(0.5 if strength == "scan" else 0.9))
    array = np.asarray(image).astype(np.float32)
    noise_rng = np.random.default_rng(rng.randrange(1 << 30))
    array += noise_rng.normal(0, 5 if strength == "scan" else 9, array.shape)
    if strength == "photo":
        gradient = np.linspace(rng.uniform(0.82, 0.95), 1.0, array.shape[1])[None, :, None]
        array *= gradient
    image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))
    if strength == "photo":
        image = image.resize((int(image.width * 0.7), int(image.height * 0.7)), Image.LANCZOS)
    return image


def write_scanned_pdf(path: Path, images: list[Image.Image]) -> None:
    doc = pymupdf.open()
    for image in images:
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=80)
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=buffer.getvalue())
    doc.save(path)
    doc.close()


# --------------------------------------------------------------------------- random invoices
class Factory:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.counter = 1000

    def number(self) -> str:
        self.counter += self.rng.randint(1, 37)
        n, style = self.counter, self.rng.randrange(4)
        return [f"INV-{n}", f"INV-2025-{n:05d}", f"SI/{n}", f"A{n:06d}"][style]

    def invoice(self, *, items: int | None = None, supplier=None, customer=None, currency=None, with_date=True,
                tax_rate=None, keys: list[str] | None = None) -> Invoice:
        rng = self.rng
        currency = currency or rng.choices(["USD", "EUR", "GBP", "BDT"], [45, 25, 20, 10])[0]
        chosen = [i for i in ITEMS if keys and i[0] in keys] if keys else rng.sample(ITEMS, min(items or rng.randint(2, 5), len(ITEMS)))
        entries = [Item(k, d, rng.randint(1, 20), q2(rng.uniform(5, 900))) for k, d, _ in chosen]
        if items and len(entries) < items:           # long invoices repeat products with different numbers
            while len(entries) < items:
                k, d, _ = rng.choice(ITEMS)
                entries.append(Item(k, d, rng.randint(1, 20), q2(rng.uniform(5, 900))))
        style = "eu" if currency == "EUR" and rng.random() < 0.5 else "sym" if currency in SYMBOLS and rng.random() < 0.3 else "plain"
        return Invoice(
            number=self.number(), date=(date(2024, 1, 1) + timedelta(days=rng.randint(0, 700))) if with_date else None,
            supplier=supplier or rng.choice(SUPPLIERS), customer=customer or rng.choice(CUSTOMERS), currency=currency,
            items=entries, tax_rate=tax_rate if tax_rate is not None else rng.choice([0, 5, 10, 15]),
            money_style=style, date_style=rng.randrange(4), discount_pct=rng.choice([0, 0, 0, 5, 10, 15]))


def copy_invoice(inv: Invoice, **changes) -> Invoice:
    data = dict(inv.__dict__)
    data.update(changes)
    return Invoice(**data)


# --------------------------------------------------------------------------- spreadsheets
HEADER_SETS = [
    ["Invoice No", "Date", "Supplier", "Customer", "Subtotal", "Discount", "Tax", "Total", "Currency"],
    ["Invoice Number", "Invoice Date", "Vendor", "Bill To", "Net Amount", "Discount Amount", "VAT", "Gross Total", "Currency"],
    ["Inv #", "Date", "Supplier Name", "Customer Name", "Sub Total", "Rebate", "Tax Amount", "Amount", "Curr"],
]


def register_rows(invoices: list[Invoice], headers: list[str], rng: random.Random):
    rows = [headers]
    for inv in invoices:
        rows.append([inv.number, inv.date.isoformat() if inv.date else "", inv.supplier, inv.customer,
                     float(inv.subtotal), float(inv.discount) if inv.discount is not None else None,
                     float(inv.tax), float(inv.total), inv.currency])
    return rows


def write_xlsx(path: Path, rows) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Invoices"
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def write_xls(path: Path, rows) -> bool:
    try:
        import xlwt
    except ImportError:
        return False
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Invoices")
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            sheet.write(r, c, value)
    workbook.save(str(path))
    return True


def write_csv(path: Path, rows, delimiter: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, delimiter=delimiter).writerows(rows)


# --------------------------------------------------------------------------- dataset
class Dataset:
    def __init__(self, out: Path, seed: int):
        self.out, self.seed = out, seed
        self.factory = Factory(seed)
        self.rng = self.factory.rng
        self.files: list[dict] = []
        self.cross_pairs: list[dict] = []
        self.n = 0

    def _name(self, label: str, ext: str) -> str:
        self.n += 1
        return f"{self.n:03d}_{label}.{ext}"

    def _record(self, name, kind, condition, invoices, expected=(), allowed=(), page_count=1):
        self.files.append({"file": name, "kind": kind, "condition": condition, "pages": page_count,
                           "invoices": [i.truth() if isinstance(i, Invoice) else i for i in invoices],
                           "expected_codes": sorted(set(expected)), "allowed_codes": sorted(set(allowed))})

    def _layout(self) -> str:
        return self.rng.choice(list(LAYOUTS))

    # ---- emitters
    def digital_pdf(self, invoices: list[Invoice], label="digital", templates: list[str] | None = None, expected=(), allowed=()):
        name = self._name(label, "pdf")
        pages = []
        for index, inv in enumerate(invoices):
            template = (templates or [self._layout()] * len(invoices))[index]
            pages += LAYOUTS[template](inv)
        write_pdf(self.out / name, pages)
        self._record(name, "digital_pdf", "digital", invoices, expected, allowed, len(pages))
        return name

    def scanned_pdf(self, inv: Invoice, strength="scan", expected=(), allowed=()):
        name = self._name("scanned", "pdf")
        template = self._layout()
        images = [degrade(render_image(ops), self.rng, strength) for ops in LAYOUTS[template](inv)]
        write_scanned_pdf(self.out / name, images)
        self._record(name, "scanned_pdf", "scan", [inv], expected, allowed, len(images))
        return name

    def image(self, inv: Invoice, fmt: str, expected=(), allowed=()):
        name = self._name("photo" if fmt == "jpg" else "image", fmt)
        template = self._layout()
        strength = "photo" if fmt == "jpg" else "scan"
        image = degrade(render_image(LAYOUTS[template](inv)[0]), self.rng, strength)
        image.save(self.out / name, "JPEG", quality=70) if fmt == "jpg" else image.save(self.out / name, "PNG")
        self._record(name, f"{fmt}_image", "photo" if fmt == "jpg" else "scan", [inv], expected, allowed)
        return name

    def tiff(self, invoices: list[Invoice]):
        name = self._name("multipage", "tiff")
        frames = [degrade(render_image(LAYOUTS[self._layout()](inv)[0]), self.rng, "scan") for inv in invoices]
        frames[0].save(self.out / name, save_all=True, append_images=frames[1:], compression="tiff_lzw")
        self._record(name, "tiff_image", "scan", invoices, page_count=len(frames))
        return name

    def sheet(self, invoices: list[Invoice], kind: str, expected=(), allowed=()):
        headers = self.rng.choice(HEADER_SETS)
        rows = register_rows(invoices, headers, self.rng)
        ext = {"xlsx": "xlsx", "xls": "xls", "csv": "csv", "csv_semicolon": "csv"}[kind]
        name = self._name(f"register_{kind}", ext)
        path = self.out / name
        if kind == "xlsx":
            write_xlsx(path, rows)
        elif kind == "xls":
            if not write_xls(path, rows):
                self.n -= 1
                return None
        else:
            write_csv(path, rows, ";" if kind == "csv_semicolon" else ",")
        self._record(name, f"{ext}_register", "sheet", invoices, expected, allowed)
        return name

    def copy_file(self, source: str, label: str, expected=(), allowed=()):
        name = self._name(label, source.rsplit(".", 1)[1])
        shutil.copyfile(self.out / source, self.out / name)
        original = next(f for f in self.files if f["file"] == source)
        self.files.append({**original, "file": name, "expected_codes": sorted(set(expected)),
                           "allowed_codes": sorted(set(allowed))})
        return name


def generate(out: Path, seed: int = 42, scale: float = 1.0) -> dict:
    """Create the dataset in ``out`` and return the ground-truth dictionary (also written to disk)."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    ds, f = Dataset(out, seed), None
    f = ds.factory
    rng = ds.rng
    k = lambda base: max(1, round(base * scale))

    # clean digital invoices in all three layouts
    for i in range(k(15)):
        ds.digital_pdf([f.invoice()], templates=["ABC"[i % 3]])
    # several invoices in one PDF
    for _ in range(k(2)):
        ds.digital_pdf([f.invoice() for _ in range(3)], label="multi_invoice")
    # one long invoice over several pages
    for _ in range(k(2)):
        ds.digital_pdf([f.invoice(items=rng.randint(28, 40))], label="long_invoice")
    # scans, photos and images
    for _ in range(k(6)):
        ds.scanned_pdf(f.invoice())
    for _ in range(k(4)):
        ds.image(f.invoice(), "png")
    for _ in range(k(4)):
        ds.image(f.invoice(), "jpg")
    ds.tiff([f.invoice(), f.invoice()])
    # spreadsheets and CSV registers
    for kind in ("xlsx", "xlsx", "xls", "csv", "csv_semicolon"):
        ds.sheet([f.invoice() for _ in range(8)], kind)

    # ---- injected problems with a known expected outcome
    for _ in range(k(3)):                                                    # printed total is wrong
        inv = f.invoice()
        inv.total_delta = q2(rng.choice([-1, 1]) * rng.uniform(5, 80))
        ds.digital_pdf([inv], label="wrong_total", expected=["TOTAL_MISMATCH"])
    for _ in range(k(2)):                                                    # no invoice date on the document
        ds.digital_pdf([f.invoice(with_date=False)], label="missing_date", expected=["MISSING_FIELD"])
    for _ in range(k(2)):                                                    # exact same file uploaded twice
        inv = f.invoice()
        original = ds.digital_pdf([inv], label="dup_original")
        ds.copy_file(original, "dup_copy", expected=["DUPLICATE_FILE"], allowed=["DUPLICATE_INVOICE"])

    # ---- the same invoice in two documents (cross-verification)
    def pair_pdf_pdf(second_kind: str, mismatch: bool):
        inv = f.invoice()
        other = copy_invoice(inv, total_delta=q2(rng.uniform(5, 60)) if mismatch else Decimal("0"),
                             date_style=(inv.date_style + 1) % 4)
        first = ds.digital_pdf([inv], label="pair_a", templates=["A"], allowed=["DUPLICATE_INVOICE"])
        expected = ["DUPLICATE_INVOICE"] + (["CROSS_CHECK_MISMATCH", "TOTAL_MISMATCH"] if mismatch else [])
        second = (ds.digital_pdf([other], label="pair_b", templates=["B"], expected=expected, allowed=["TOTAL_MISMATCH", "CROSS_CHECK_MISMATCH"])
                  if second_kind == "digital" else ds.scanned_pdf(other, expected=["DUPLICATE_INVOICE"] + (["CROSS_CHECK_MISMATCH"] if mismatch else []),
                                                                   allowed=["TOTAL_MISMATCH", "CROSS_CHECK_MISMATCH", "LOW_OCR_CONFIDENCE"]))
        # the earlier PDF is also flagged when the later one is processed (cross-check mismatch is symmetric)
        if mismatch:
            next(x for x in ds.files if x["file"] == first)["allowed_codes"] += ["CROSS_CHECK_MISMATCH"]
        ds.cross_pairs.append({"files": [first, second], "invoice_number": inv.number,
                               "expected_outcome": "mismatch" if mismatch else "match", "type": "pdf_pdf"})

    pair_pdf_pdf("digital", False)
    pair_pdf_pdf("digital", False)
    pair_pdf_pdf("scan", False)
    pair_pdf_pdf("digital", True)

    def pair_pdf_excel(mismatch: bool, kind: str = "xlsx"):
        invoices = [f.invoice() for _ in range(2)]
        pdfs = [ds.digital_pdf([inv], label="xpair_pdf", allowed=["CROSS_CHECK_MISMATCH"]) for inv in invoices]
        register_invoices = []
        for index, inv in enumerate(invoices):
            changed = copy_invoice(inv, total_delta=q2(rng.uniform(5, 60)) if (mismatch and index == 0) else Decimal("0"))
            register_invoices.append(changed)
            ds.cross_pairs.append({"files": [pdfs[index], None], "invoice_number": inv.number,
                                   "expected_outcome": "mismatch" if (mismatch and index == 0) else "match", "type": "pdf_excel"})
        register_invoices += [f.invoice() for _ in range(3)]
        sheet = ds.sheet(register_invoices, kind, expected=(["CROSS_CHECK_MISMATCH", "TOTAL_MISMATCH"] if mismatch else []),
                         allowed=["TOTAL_MISMATCH", "CROSS_CHECK_MISMATCH"])
        for pair in ds.cross_pairs[-2:]:
            pair["files"][1] = sheet

    pair_pdf_excel(False)
    pair_pdf_excel(False, "csv")
    pair_pdf_excel(True)
    pair_pdf_excel(True, "csv")

    # ---- search ground truth: which files contain which invoice, supplier and product
    queries = build_queries(ds)
    truth = {
        "meta": {"seed": seed, "scale": scale, "files": len(ds.files), "invoices": sum(len(x["invoices"]) for x in ds.files),
                 "note": "Synthetic data with fictional companies. Ground truth is exact by construction."},
        "files": ds.files, "cross_pairs": ds.cross_pairs, "search_queries": queries,
    }
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    return truth


def build_queries(ds: Dataset) -> list[dict]:
    by_number: dict[str, set] = {}
    by_supplier: dict[str, set] = {}
    by_item: dict[str, set] = {}
    for entry in ds.files:
        for inv in entry["invoices"]:
            by_number.setdefault(inv["invoice_number"], set()).add(entry["file"])
            by_supplier.setdefault(inv["supplier_name"], set()).add(entry["file"])
            for key in set(inv.get("items", [])):
                by_item.setdefault(key, set()).add(entry["file"])
    rng = random.Random(ds.seed + 1)
    queries = []
    for number in rng.sample(sorted(by_number), min(20, len(by_number))):
        queries.append({"type": "invoice_number", "query": number, "relevant": sorted(by_number[number])})
    for supplier in rng.sample(sorted(by_supplier), min(10, len(by_supplier))):
        words = supplier.split()
        queries.append({"type": "supplier", "query": " ".join(words[:2]).lower(), "relevant": sorted(by_supplier[supplier])})
    for key, _, paraphrases in ITEMS:
        if key in by_item:
            for text in paraphrases:
                queries.append({"type": "item_paraphrase", "query": text, "relevant": sorted(by_item[key])})
    return queries


def generate_stress_pdf(path: Path, pages: int = 1000, pages_per_invoice: int = 5, seed: int = 7) -> int:
    """A large digital PDF made of many multi-page invoices. Returns the number of invoices."""
    factory = Factory(seed)
    count = max(1, pages // pages_per_invoice)
    doc = pymupdf.open()
    for _ in range(count):
        inv = factory.invoice(items=pages_per_invoice * 14 - 6)
        for ops in layout_a(inv):
            page = doc.new_page()
            for x, y, text, size, bold in ops:
                page.insert_text((x, y), text, fontsize=size, fontname="hebo" if bold else "helv")
    doc.save(path, deflate=True)
    doc.close()
    return count
