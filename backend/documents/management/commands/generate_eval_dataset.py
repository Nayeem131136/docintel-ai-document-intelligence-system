"""Create the synthetic evaluation dataset (files + ground_truth.json).

    python manage.py generate_eval_dataset --out eval_data --seed 42
"""
from pathlib import Path

from django.core.management.base import BaseCommand

from evaluation.generator import generate


class Command(BaseCommand):
    help = "Generate synthetic invoices (PDF, scans, images, spreadsheets) with exact ground truth for evaluation."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="eval_data", help="Output folder (it is replaced if it exists).")
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--scale", type=float, default=1.0, help="Multiplier for the number of files (1.0 = about 70 files).")

    def handle(self, *args, **options):
        out = Path(options["out"]).resolve()
        truth = generate(out, seed=options["seed"], scale=options["scale"])
        meta = truth["meta"]
        self.stdout.write(self.style.SUCCESS(f"Created {meta['files']} files with {meta['invoices']} invoices in {out}"))
        self.stdout.write("Ground truth: ground_truth.json (do not upload this file to the app).")
