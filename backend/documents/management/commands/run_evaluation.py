"""Measure accuracy and speed of the real pipeline on a generated dataset and write a report.

    python manage.py run_evaluation --data eval_data --report ../docs/EVALUATION_REPORT.md
    python manage.py run_evaluation --data eval_data --no-llm --stress-pages 1000

Uses a throw-away database and media folder: your own documents are never touched.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from evaluation.report import build_report
from evaluation.runner import run_evaluation


class Command(BaseCommand):
    help = "Run the evaluation dataset through the pipeline and write the report (Markdown) and raw results (JSON)."

    def add_arguments(self, parser):
        parser.add_argument("--data", default="eval_data", help="Folder created by generate_eval_dataset.")
        parser.add_argument("--report", default="EVALUATION_REPORT.md", help="Markdown report to write.")
        parser.add_argument("--json-out", help="Raw results JSON (default: next to the report).")
        parser.add_argument("--no-llm", action="store_true", help="Rule-based extraction only (no API calls).")
        parser.add_argument("--stress-pages", type=int, default=0, help="Also time one PDF with this many pages (e.g. 1000).")
        parser.add_argument("--stress-llm", action="store_true", help="Use the LLM for the stress PDF too (one API call per invoice).")

    def handle(self, *args, **options):
        data = Path(options["data"]).resolve()
        if not (data / "ground_truth.json").exists():
            raise CommandError(f"{data} has no ground_truth.json. Run generate_eval_dataset first.")
        result = run_evaluation(data, use_llm=not options["no_llm"], stress_pages=options["stress_pages"],
                                stress_llm=options["stress_llm"], progress=self.stdout.write)
        report = Path(options["report"]).resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(build_report(result), encoding="utf-8")
        json_path = Path(options["json_out"]).resolve() if options["json_out"] else report.with_suffix(".json")
        json_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        overall = result["extraction"]["overall"]
        self.stdout.write(self.style.SUCCESS(
            f"Done. Field precision {overall['precision']:.1%}, recall {overall['recall']:.1%}. Report: {report}"))
