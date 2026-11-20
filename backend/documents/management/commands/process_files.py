"""Process local files (or whole folders) through the full pipeline:
text extraction / OCR -> AI extraction -> validation -> cross-verification.

    python manage.py process_files path/to/invoice.pdf path/to/folder
    python manage.py process_files invoice.pdf --show-text --no-llm
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from documents.orchestrator import process_document
from documents.processing import ProcessingError, create_document_from_path
from documents.processing.detect import EXTENSION_TYPES


class Command(BaseCommand):
    help = "Run the full document pipeline on local files and print the extracted invoices and issues."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Files or folders to process.")
        parser.add_argument("--show-text", action="store_true", help="Print the extracted text of every page.")
        parser.add_argument("--json-out", help="Write a JSON summary to this file.")
        parser.add_argument("--no-llm", action="store_true", help="Skip the LLM and use rule-based extraction only.")

    def handle(self, *args, **options):
        files = self._collect(options["paths"])
        if not files:
            self.stderr.write(self.style.ERROR("No supported files found."))
            return

        summary = []
        self.stdout.write(f"{'FILE':40} {'TYPE':6} {'STATUS':13} {'PAGES':>6} {'TIME(ms)':>9}")
        for path in files:
            try:
                document = create_document_from_path(path)
            except ProcessingError as exc:
                self.stdout.write(f"{path.name[:40]:40} {'-':6} {'rejected':13} {'-':>6} {'-':>9}  {exc}")
                summary.append({"file": path.name, "status": "rejected", "error": str(exc)})
                continue
            process_document(document, **({"llm": None} if options["no_llm"] else {}))
            self.stdout.write(
                f"{path.name[:40]:40} {document.file_type:6} {document.status:13} "
                f"{document.page_count:>6} {document.processing_time_ms or 0:>9}"
                + (f"  {document.error_message}" if document.error_message else "")
            )
            invoices = []
            for result in document.results.all():
                self.stdout.write(
                    f"    invoice {result.invoice_number or '?'} | {result.supplier_name or '?'} | "
                    f"{result.invoice_date or '?'} | total {result.total if result.total is not None else '?'} "
                    f"{result.currency or ''} | {result.method} | {result.review_status}")
                for issue in result.issues.filter(severity__in=("error", "warning")):
                    self.stdout.write(f"        [{issue.severity}] {issue.code}: {issue.message}")
                invoices.append({"invoice_number": result.invoice_number, "supplier": result.supplier_name,
                                 "date": str(result.invoice_date) if result.invoice_date else None,
                                 "total": str(result.total) if result.total is not None else None,
                                 "currency": result.currency, "review_status": result.review_status,
                                 "issues": list(result.issues.values_list("code", flat=True))})
            for issue in document.issues.filter(result__isnull=True):
                self.stdout.write(f"    [{issue.severity}] {issue.code}: {issue.message}")
            summary.append(
                {
                    "file": path.name,
                    "type": document.file_type,
                    "status": document.status,
                    "pages": document.page_count,
                    "time_ms": document.processing_time_ms,
                    "error": document.error_message,
                    "invoices": invoices,
                }
            )
            if options["show_text"]:
                for page in document.pages.all():
                    label = f"[{page.source}" + (f", conf {page.ocr_confidence:.2f}" if page.ocr_confidence else "") + "]"
                    title = f"page {page.page_number}" + (f" ({page.sheet_name})" if page.sheet_name else "")
                    self.stdout.write(f"--- {title} {label}\n{page.text}\n")

        if options["json_out"]:
            Path(options["json_out"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
            self.stdout.write(f"Summary written to {options['json_out']}")

    @staticmethod
    def _collect(paths):
        files = []
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                files += sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSION_TYPES)
            elif path.is_file():
                files.append(path)
        return files
