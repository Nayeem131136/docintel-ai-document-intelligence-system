"""Process local files (or whole folders) through the text-extraction pipeline.

    python manage.py process_files path/to/invoice.pdf path/to/folder --show-text
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from documents.processing import ProcessingError, create_document_from_path, extract_document_text
from documents.processing.detect import EXTENSION_TYPES


class Command(BaseCommand):
    help = "Run text extraction / OCR / spreadsheet parsing on local files and print a summary."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Files or folders to process.")
        parser.add_argument("--show-text", action="store_true", help="Print the extracted text of every page.")
        parser.add_argument("--json-out", help="Write a JSON summary to this file.")

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
            extract_document_text(document)
            self.stdout.write(
                f"{path.name[:40]:40} {document.file_type:6} {document.status:13} "
                f"{document.page_count:>6} {document.processing_time_ms or 0:>9}"
                + (f"  {document.error_message}" if document.error_message else "")
            )
            summary.append(
                {
                    "file": path.name,
                    "type": document.file_type,
                    "status": document.status,
                    "pages": document.page_count,
                    "time_ms": document.processing_time_ms,
                    "error": document.error_message,
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
