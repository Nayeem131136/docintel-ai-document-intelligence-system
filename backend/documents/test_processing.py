"""Tests for the document-processing pipelines.

All fixtures are generated in code (no binary files are committed): digital PDFs with
PyMuPDF, scanned PDFs / images by drawing text with Pillow, spreadsheets with
openpyxl / xlwt. OCR tests run the real OCR engine.
"""
import io
import shutil
import tempfile
import time
import unittest
import zipfile
from datetime import date
from pathlib import Path

import pymupdf
from django.test import SimpleTestCase, TestCase, override_settings
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .models import Document, ProcessingEvent
from .processing import (
    CorruptedFileError,
    FileTooLargeError,
    UnsupportedFileError,
    create_document_from_path,
    detect_file_type,
    extract_document_text,
)
from .processing.ocr import _assemble

try:
    import xlwt
except ImportError:  # pragma: no cover
    xlwt = None

INVOICE_LINES = ["INVOICE No: INV-2026-0042", "Supplier: Acme Trading Ltd", "Total: USD 1,150.00"]


def text_image(lines=INVOICE_LINES, size=(1000, 360), font_size=40) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=font_size)
    for index, line in enumerate(lines):
        draw.text((30, 30 + index * 100), line, font=font, fill="black")
    return image


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def digital_pdf(path: Path, pages: list[str]):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 100), text, fontsize=12)
    doc.save(path)
    doc.close()


def a4_scan(lines=INVOICE_LINES) -> Image.Image:
    """Text on a white A4-proportioned canvas (like a real 150 dpi scan)."""
    return text_image(lines, size=(1240, 1754), font_size=44)


def scanned_pdf(path: Path, images: list[Image.Image]):
    """A PDF whose pages are only pictures (no text layer), like a scan."""
    doc = pymupdf.open()
    for image in images:
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=png_bytes(image))
    doc.save(path)
    doc.close()


def norm(text: str) -> str:
    return " ".join(text.split()).lower()


class MediaTestCase(TestCase):
    """Runs each test with a throw-away MEDIA_ROOT and a temp folder for fixtures."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.media = Path(tempfile.mkdtemp())
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(shutil.rmtree, self.media, True)

    def run_file(self, path: Path, name: str | None = None) -> Document:
        document = create_document_from_path(path, name)
        return extract_document_text(document)

    def page_texts(self, document):
        return [p.text for p in document.pages.all()]


# ---------------------------------------------------------------- detection / validation
class DetectFileTypeTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, name, data: bytes) -> Path:
        path = self.tmp / name
        path.write_bytes(data)
        return path

    def test_detects_supported_types_from_content(self):
        digital_pdf(self.tmp / "a.pdf", ["hello"])
        text_image().save(self.tmp / "a.png")
        text_image().save(self.tmp / "a.jpg")
        text_image().save(self.tmp / "a.tiff")
        wb = Workbook()
        wb.save(self.tmp / "a.xlsx")
        (self.tmp / "a.csv").write_text("a,b\n1,2\n")
        expected = {"a.pdf": "pdf", "a.png": "image", "a.jpg": "image", "a.tiff": "image",
                    "a.xlsx": "xlsx", "a.csv": "csv"}
        for name, kind in expected.items():
            self.assertEqual(detect_file_type(self.tmp / name), kind, name)

    def test_rejects_unsupported_extension(self):
        path = self.write("report.docx", b"PK\x03\x04 anything")
        with self.assertRaises(UnsupportedFileError):
            detect_file_type(path)

    def test_rejects_empty_file(self):
        with self.assertRaisesMessage(CorruptedFileError, "empty"):
            detect_file_type(self.write("empty.pdf", b""))

    def test_rejects_content_that_does_not_match_extension(self):
        with self.assertRaises(CorruptedFileError):
            detect_file_type(self.write("fake.pdf", b"this is just text, not a pdf"))
        digital_pdf(self.tmp / "real.pdf", ["x"])
        (self.tmp / "disguised.png").write_bytes((self.tmp / "real.pdf").read_bytes())
        with self.assertRaises(CorruptedFileError):
            detect_file_type(self.tmp / "disguised.png")

    def test_rejects_binary_masquerading_as_csv(self):
        with self.assertRaises(CorruptedFileError):
            detect_file_type(self.write("data.csv", b"%PDF-1.7\n" + bytes(200)))

    def test_xls_extension_with_xlsx_content_is_accepted_as_xlsx(self):
        Workbook().save(self.tmp / "wrongext.xls")
        self.assertEqual(detect_file_type(self.tmp / "wrongext.xls"), "xlsx")

    @override_settings(MAX_UPLOAD_SIZE_MB=1)
    def test_rejects_oversized_file(self):
        path = self.write("big.csv", b"a,b\n" + b"1,2\n" * 400_000)
        with self.assertRaises(FileTooLargeError):
            detect_file_type(path)


# ---------------------------------------------------------------- PDF
class PdfPipelineTests(MediaTestCase):
    def test_multi_page_digital_pdf_uses_text_layer_not_ocr(self):
        path = self.tmp / "digital.pdf"
        digital_pdf(path, ["Invoice INV-001 total 100.00 for Acme Supplies", "Page two: invoice INV-002 total 250.00 customer Globex",
                           "Page three: invoice INV-003 total 75.50 supplier Initech"])
        document = self.run_file(path)

        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.assertEqual(document.page_count, 3)
        self.assertEqual(document.progress, 100)
        pages = list(document.pages.all())
        self.assertEqual([p.source for p in pages], ["digital"] * 3)
        self.assertIn("INV-002", pages[1].text)
        self.assertIsNone(pages[0].ocr_confidence)
        self.assertIsNotNone(document.processing_time_ms)

    def test_scanned_pdf_is_read_with_ocr(self):
        path = self.tmp / "scan.pdf"
        scanned_pdf(path, [a4_scan()])
        document = self.run_file(path)

        self.assertEqual(document.status, Document.Status.COMPLETED)
        page = document.pages.get()
        self.assertEqual(page.source, "ocr")
        self.assertIn("inv-2026-0042", norm(page.text))
        self.assertIn("1,150.00", page.text)
        self.assertGreater(page.ocr_confidence, 0.5)

    def test_mixed_pdf_uses_digital_and_ocr_per_page(self):
        path = self.tmp / "mixed.pdf"
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 100), "Digital page with plenty of readable text: invoice INV-9 total 10.00", fontsize=12)
        scan = doc.new_page(width=595, height=842)
        scan.insert_image(scan.rect, stream=png_bytes(a4_scan()))
        doc.save(path)
        doc.close()

        document = self.run_file(path)
        self.assertEqual([p.source for p in document.pages.all()], ["digital", "ocr"])

    def test_blank_page_is_not_an_error_and_is_not_ocrd(self):
        path = self.tmp / "blank.pdf"
        digital_pdf(path, ["Real page with enough text to count as digital content here", ""])
        document = self.run_file(path)

        self.assertEqual(document.status, Document.Status.COMPLETED)
        blank = document.pages.get(page_number=2)
        self.assertEqual(blank.text.strip(), "")
        self.assertEqual(blank.source, "digital")
        self.assertFalse(blank.has_error)

    def test_thousand_page_pdf_is_processed_in_batches(self):
        path = self.tmp / "big.pdf"
        digital_pdf(path, [f"Page {i}: invoice INV-{i:05d} total {i}.00 supplier Acme" for i in range(1, 1001)])
        started = time.perf_counter()
        document = self.run_file(path)
        elapsed = time.perf_counter() - started

        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.assertEqual(document.page_count, 1000)
        self.assertEqual(document.pages.count(), 1000)
        self.assertIn("INV-00777", document.pages.get(page_number=777).text)
        print(f"\n[1000-page digital PDF extracted in {elapsed:.1f}s]")

    def test_corrupted_pdf_fails_cleanly(self):
        path = self.tmp / "broken.pdf"
        path.write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 20)
        document = self.run_file(path)

        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertTrue(document.error_message)
        self.assertEqual(document.pages.count(), 0)

    def test_password_protected_pdf_fails_with_clear_message(self):
        path = self.tmp / "locked.pdf"
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 100), "secret", fontsize=12)
        doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
        doc.close()

        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertIn("password", document.error_message.lower())

    @override_settings(MAX_PDF_PAGES=2)
    def test_pdf_over_page_limit_is_rejected(self):
        path = self.tmp / "long.pdf"
        digital_pdf(path, ["one one one one one one one one", "two two two two two two two two", "three three three three"])
        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertIn("limit", document.error_message)


# ---------------------------------------------------------------- Images / OCR
class ImagePipelineTests(MediaTestCase):
    def check_invoice_text(self, document):
        self.assertEqual(document.status, Document.Status.COMPLETED, document.error_message)
        text = norm(document.pages.get().text)
        self.assertIn("inv-2026-0042", text)
        self.assertIn("acme trading ltd", text)
        self.assertIn("1,150.00", text)

    def test_png_is_ocrd(self):
        path = self.tmp / "invoice.png"
        text_image().save(path)
        self.check_invoice_text(self.run_file(path))

    def test_jpg_is_ocrd(self):
        path = self.tmp / "invoice.jpg"
        text_image().save(path, quality=92)
        self.check_invoice_text(self.run_file(path))

    def test_tiff_is_ocrd(self):
        path = self.tmp / "invoice.tiff"
        text_image().save(path)
        self.check_invoice_text(self.run_file(path))

    def test_multi_page_tiff_gives_one_page_per_frame(self):
        path = self.tmp / "multi.tif"
        first = text_image(["INVOICE No: INV-AAA-111", "Total: USD 10.00"])
        second = text_image(["INVOICE No: INV-BBB-222", "Total: USD 20.00"])
        first.save(path, save_all=True, append_images=[second])

        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.assertEqual(document.page_count, 2)
        pages = list(document.pages.all())
        self.assertIn("inv-aaa-111", norm(pages[0].text))
        self.assertIn("inv-bbb-222", norm(pages[1].text))

    def test_table_row_stays_on_one_line(self):
        image = Image.new("RGB", (1200, 220), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=40)
        for x, word in [(40, "Widget"), (500, "2"), (700, "50.00"), (950, "100.00")]:
            draw.text((x, 80), word, font=font, fill="black")
        path = self.tmp / "row.png"
        image.save(path)

        text = self.run_file(path).pages.get().text
        self.assertEqual(len(text.strip().splitlines()), 1, text)
        self.assertIn("Widget", text)
        self.assertIn("100.00", text)

    def test_noisy_low_contrast_image_still_processes(self):
        """Poor quality input must not crash; the pipeline still returns text and a confidence."""
        image = text_image().convert("L").filter(ImageFilter.GaussianBlur(1.3))
        image = Image.eval(image, lambda v: 110 + v // 3)   # washed-out contrast
        path = self.tmp / "poor.png"
        image.convert("RGB").save(path)

        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.COMPLETED, document.error_message)
        page = document.pages.get()
        self.assertIsNotNone(page.ocr_confidence)
        self.assertIn("invoice", norm(page.text))

    def test_rotated_scan_is_recovered(self):
        path = self.tmp / "rotated.png"
        text_image().rotate(90, expand=True).save(path)
        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.assertIn("inv-2026-0042", norm(document.pages.get().text))

    def test_blank_image_completes_with_empty_text(self):
        path = self.tmp / "blank.png"
        Image.new("RGB", (800, 600), "white").save(path)
        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.assertEqual(document.pages.get().text.strip(), "")

    def test_truncated_image_fails_cleanly(self):
        good = self.tmp / "good.png"
        text_image(size=(1200, 800)).save(good)
        data = good.read_bytes()
        broken = self.tmp / "truncated.png"
        broken.write_bytes(data[: len(data) // 3])

        document = self.run_file(broken)
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertTrue(document.error_message)

    def test_garbage_bytes_named_png_fail_cleanly(self):
        path = self.tmp / "garbage.png"
        path.write_bytes(bytes(range(256)) * 50)
        with self.assertRaises(CorruptedFileError):       # rejected up front, no Document created
            create_document_from_path(path)
        self.assertEqual(Document.objects.count(), 0)


class OcrAssemblyTests(SimpleTestCase):
    def box(self, x, y, w=100, h=20):
        return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]

    def test_groups_boxes_into_lines_left_to_right(self):
        raw = [
            (self.box(300, 12), "50.00", 0.9),
            (self.box(10, 10), "Widget", 0.9),
            (self.box(10, 60), "Gadget", 0.8),
            (self.box(300, 62), "75.00", 0.8),
        ]
        result = _assemble(raw)
        self.assertEqual(result.text, "Widget  50.00\nGadget  75.00")
        self.assertAlmostEqual(result.confidence, 0.85)

    def test_empty_result(self):
        result = _assemble(None)
        self.assertEqual(result.text, "")
        self.assertIsNone(result.confidence)


# ---------------------------------------------------------------- Spreadsheets
class SpreadsheetPipelineTests(MediaTestCase):
    def test_xlsx_with_multiple_sheets(self):
        wb = Workbook()
        first = wb.active
        first.title = "Invoices"
        first.append(["Invoice No", "Date", "Total"])
        first.append(["INV-1", date(2026, 3, 1), 115.5])
        first.append([])                       # empty row is skipped
        first.append(["INV-2", date(2026, 3, 2), 200])
        second = wb.create_sheet("Notes")
        second.append(["Prepared by", "Finance"])
        path = self.tmp / "book.xlsx"
        wb.save(path)

        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.assertEqual(document.page_count, 2)
        invoices, notes = list(document.pages.all())
        self.assertEqual(invoices.sheet_name, "Invoices")
        self.assertEqual(invoices.source, "spreadsheet")
        self.assertEqual(invoices.table["rows"][0], ["Invoice No", "Date", "Total"])
        self.assertEqual(invoices.table["rows"][1], ["INV-1", "2026-03-01", 115.5])
        self.assertEqual(invoices.table["rows"][2], ["INV-2", "2026-03-02", 200])
        self.assertIn("INV-1 | 2026-03-01 | 115.5", invoices.text)
        self.assertEqual(notes.sheet_name, "Notes")

    @override_settings(MAX_SPREADSHEET_ROWS=3)
    def test_large_sheet_is_truncated_with_warning(self):
        wb = Workbook()
        for index in range(10):
            wb.active.append([f"row{index}", index])
        path = self.tmp / "long.xlsx"
        wb.save(path)

        document = self.run_file(path)
        page = document.pages.get()
        self.assertEqual(len(page.table["rows"]), 3)
        self.assertTrue(page.table["truncated"])
        self.assertIn("truncated", page.error_message.lower())
        self.assertFalse(page.has_error)

    @unittest.skipIf(xlwt is None, "xlwt not installed (pip install -r requirements-dev.txt)")
    def test_legacy_xls(self):
        wb = xlwt.Workbook()
        sheet = wb.add_sheet("Legacy")
        sheet.write(0, 0, "Invoice")
        sheet.write(0, 1, "Amount")
        sheet.write(1, 0, "INV-77")
        sheet.write(1, 1, 99.5)
        sheet.write(2, 0, "INV-78")
        sheet.write(2, 1, 100)
        other = wb.add_sheet("Second")
        other.write(0, 0, "x")
        path = self.tmp / "old.xls"
        wb.save(str(path))

        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.COMPLETED, document.error_message)
        self.assertEqual(document.page_count, 2)
        legacy = document.pages.get(page_number=1)
        self.assertEqual(legacy.sheet_name, "Legacy")
        self.assertEqual(legacy.table["rows"], [["Invoice", "Amount"], ["INV-77", 99.5], ["INV-78", 100]])

    def test_csv_comma(self):
        path = self.tmp / "a.csv"
        path.write_text("Invoice,Total\nINV-1,100.50\nINV-2,20\n", encoding="utf-8")
        page = self.run_file(path).pages.get()
        self.assertEqual(page.table["rows"], [["Invoice", "Total"], ["INV-1", "100.50"], ["INV-2", "20"]])

    def test_csv_semicolon_delimiter(self):
        path = self.tmp / "eu.csv"
        path.write_text("Rechnung;Betrag\nR-1;100,50\nR-2;20\n", encoding="utf-8")
        page = self.run_file(path).pages.get()
        self.assertEqual(page.table["rows"][1], ["R-1", "100,50"])

    def test_csv_with_utf8_bom_has_clean_header(self):
        path = self.tmp / "bom.csv"
        path.write_bytes(b"\xef\xbb\xbfInvoice,Total\nINV-1,5\n")
        rows = self.run_file(path).pages.get().table["rows"]
        self.assertEqual(rows[0][0], "Invoice")

    def test_csv_cp1252_encoding(self):
        path = self.tmp / "win.csv"
        path.write_bytes("Fournisseur,Total\nCafé Müller,€100\n".encode("cp1252"))
        rows = self.run_file(path).pages.get().table["rows"]
        self.assertEqual(rows[1], ["Café Müller", "€100"])

    def test_csv_quoted_multiline_cell(self):
        path = self.tmp / "multi.csv"
        path.write_text('Name,Address\nAcme,"1 Main St\nDhaka"\n', encoding="utf-8")
        rows = self.run_file(path).pages.get().table["rows"]
        self.assertEqual(rows[1], ["Acme", "1 Main St\nDhaka"])

    def test_csv_with_nul_bytes_is_rejected_as_binary(self):
        path = self.tmp / "bin.csv"
        path.write_bytes(b"a,b\n1,2\x00\x00\x00\n" + bytes(50))
        with self.assertRaises(CorruptedFileError):
            create_document_from_path(path)

    def test_whitespace_only_csv_fails(self):
        path = self.tmp / "blank.csv"
        path.write_text("   \n\n  \n", encoding="utf-8")
        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.FAILED)

    def test_corrupted_xlsx_fails_cleanly(self):
        path = self.tmp / "broken.xlsx"
        good = self.tmp / "good.xlsx"
        wb = Workbook()
        wb.active.append(["a", "b"] * 50)
        wb.save(good)
        path.write_bytes(good.read_bytes()[:200])          # truncated zip

        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertTrue(document.error_message)

    def test_xlsx_that_is_a_zip_but_not_a_workbook_fails_cleanly(self):
        path = self.tmp / "notbook.xlsx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("hello.txt", "not a workbook")
        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.FAILED)

    @override_settings(MAX_UNCOMPRESSED_MB=1)
    def test_zip_bomb_xlsx_is_rejected(self):
        path = self.tmp / "bomb.xlsx"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("xl/big.xml", b"0" * (3 * 1024 * 1024))
        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertIn("safety limit", document.error_message)

    def test_garbage_xls_fails_cleanly(self):
        path = self.tmp / "garbage.xls"
        path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(range(256)) * 10)
        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.FAILED)


# ---------------------------------------------------------------- Pipeline behaviour
class PipelineBehaviourTests(MediaTestCase):
    def test_unsupported_file_is_rejected_before_a_document_is_created(self):
        path = self.tmp / "notes.docx"
        path.write_bytes(b"PK\x03\x04 hello")
        with self.assertRaises(UnsupportedFileError):
            create_document_from_path(path)
        self.assertEqual(Document.objects.count(), 0)

    def test_history_records_every_stage(self):
        path = self.tmp / "a.csv"
        path.write_text("a,b\n1,2\n")
        document = self.run_file(path)

        events = list(document.events.values_list("stage", "outcome"))
        self.assertEqual(
            events,
            [("upload", "success"), ("text_extraction", "started"), ("text_extraction", "success")],
        )
        self.assertIsNotNone(document.events.last().duration_ms)

    def test_failed_document_history_records_the_failure(self):
        path = self.tmp / "bad.pdf"
        path.write_bytes(b"%PDF-1.4 garbage" + bytes(300))
        document = self.run_file(path)
        last = document.events.last()
        self.assertEqual((last.stage, last.outcome), ("text_extraction", "failed"))
        self.assertTrue(last.message)

    def test_reprocessing_replaces_pages_and_counts_attempts(self):
        path = self.tmp / "a.csv"
        path.write_text("a,b\n1,2\n")
        document = self.run_file(path)
        self.assertEqual(document.attempts, 1)

        extract_document_text(document)
        document.refresh_from_db()
        self.assertEqual(document.attempts, 2)
        self.assertEqual(document.pages.count(), 1)
        self.assertEqual(document.status, Document.Status.COMPLETED)

    def test_reprocessing_recovers_after_a_failed_attempt(self):
        path = self.tmp / "a.csv"
        path.write_text("a,b\n1,2\n")
        document = create_document_from_path(path)
        stored = Path(document.file.path)
        original = stored.read_bytes()
        stored.write_bytes(b"")                                  # simulate a damaged upload
        extract_document_text(document)
        self.assertEqual(document.status, Document.Status.FAILED)

        stored.write_bytes(original)                             # fixed -> reprocess
        extract_document_text(document)
        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.assertEqual(document.error_message, "")

    def test_wrong_extension_for_excel_family_is_handled(self):
        wb = Workbook()
        wb.active.append(["x", 1])
        path = self.tmp / "actually_xlsx.xls"
        wb.save(path)
        document = self.run_file(path)
        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.assertEqual(document.file_type, "xlsx")

    def test_nul_and_crlf_are_cleaned_so_postgres_can_store_text(self):
        from .processing.base import clean_text
        self.assertEqual(clean_text("a\x00b\r\nc\rd"), "ab\nc\nd")

    def test_progress_and_counters_are_updated(self):
        path = self.tmp / "p.pdf"
        digital_pdf(path, [f"Page {i} with sufficient text content for digital extraction" for i in range(45)])
        document = self.run_file(path)
        self.assertEqual(document.pages_processed, 45)
        self.assertEqual(document.progress, 100)
