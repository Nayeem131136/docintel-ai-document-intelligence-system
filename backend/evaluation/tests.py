"""Tests for the evaluation tooling itself (scoring maths, dataset generator, report)."""
import json
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pymupdf
from django.core.management import call_command
from django.test import SimpleTestCase

from . import metrics
from .generator import Factory, generate, generate_stress_pdf, q2
from .report import build_report


class FieldComparisonTests(SimpleTestCase):
    def test_outcomes(self):
        c = metrics.compare_field
        self.assertEqual(c("total", "100.00", "100"), "correct")
        self.assertEqual(c("total", "100.00", "100.005"), "correct")          # within a cent
        self.assertEqual(c("total", "100.00", "100.50"), "wrong")
        self.assertEqual(c("total", "100.00", None), "missing")
        self.assertEqual(c("invoice_date", None, "2025-01-01"), "spurious")
        self.assertEqual(c("invoice_date", None, None), "empty")
        self.assertEqual(c("supplier_name", "Acme Trading Ltd", "ACME trading, Ltd."), "correct")
        self.assertEqual(c("currency", "USD", "usd"), "correct")
        self.assertEqual(c("invoice_number", "INV-1", "INV-2"), "wrong")

    def test_precision_recall_f1(self):
        r = metrics.prf(correct=8, wrong=2, missing=10)
        self.assertAlmostEqual(r["precision"], 0.8)
        self.assertAlmostEqual(r["recall"], 0.4)
        self.assertAlmostEqual(r["f1"], 2 * 0.8 * 0.4 / 1.2)
        self.assertIsNone(metrics.prf(0, 0, 0)["precision"])
        self.assertEqual(metrics.prf(0, 3, 0)["f1"], 0.0)

    def test_percentile_and_reciprocal_rank(self):
        self.assertEqual(metrics.percentile([5, 1, 3, 2, 4], 0.5), 3)
        self.assertIsNone(metrics.percentile([], 0.5))
        self.assertEqual(metrics.reciprocal_rank(["a", "b", "c"], {"b"}), 0.5)
        self.assertEqual(metrics.reciprocal_rank(["a"], {"z"}), 0.0)


def truth_invoice(number="INV-1", **overrides):
    base = {"invoice_number": number, "invoice_date": "2025-01-01", "supplier_name": "Acme", "customer_name": "Globex",
            "currency": "USD", "subtotal": "100.00", "tax": "10.00", "total": "110.00", "item_count": 2, "items": []}
    return {**base, **overrides}


class MatchingTests(SimpleTestCase):
    def test_matches_by_number_then_by_order(self):
        truths = [truth_invoice("A-1"), truth_invoice("B-2"), truth_invoice("C-3")]
        preds = [{"invoice_number": "b2"}, {"invoice_number": "WRONG"}]
        pairs, missed, extra = metrics.match_invoices(truths, preds)
        self.assertEqual([(t["invoice_number"], p["invoice_number"]) for t, p in pairs], [("B-2", "b2"), ("A-1", "WRONG")])
        self.assertEqual([m["invoice_number"] for m in missed], ["C-3"])
        self.assertEqual(extra, [])

    def test_extra_predictions(self):
        _, missed, extra = metrics.match_invoices([truth_invoice("A-1")], [{"invoice_number": "A-1"}, {"invoice_number": "Z-9"}])
        self.assertEqual((len(missed), len(extra)), (0, 1))


class ScoringTests(SimpleTestCase):
    files = [
        {"file": "a.pdf", "kind": "digital_pdf", "condition": "digital", "invoices": [truth_invoice("A-1")],
         "expected_codes": [], "allowed_codes": []},
        {"file": "b.pdf", "kind": "digital_pdf", "condition": "digital", "invoices": [truth_invoice("B-2", invoice_date=None)],
         "expected_codes": ["MISSING_FIELD"], "allowed_codes": []},
    ]

    def outputs(self, **changes):
        good = {"invoice_number": "A-1", "invoice_date": "2025-01-01", "supplier_name": "Acme", "customer_name": "Globex",
                "currency": "USD", "subtotal": "100.00", "tax": "10.00", "total": "110.00", "item_count": 2}
        return {"a.pdf": {"invoices": [{**good, **changes}], "issue_codes": []},
                "b.pdf": {"invoices": [{**good, "invoice_number": "B-2", "invoice_date": None}], "issue_codes": ["MISSING_FIELD"]}}

    def test_perfect_extraction(self):
        result = metrics.score_extraction(self.files, self.outputs())
        self.assertEqual(result["overall"]["precision"], 1.0)
        self.assertEqual(result["fully_correct_invoices"], 2)
        self.assertEqual(result["invoice_detection"]["recall"], 1.0)
        self.assertEqual(result["errors"], [])

    def test_wrong_missing_and_invented_values_are_counted(self):
        result = metrics.score_extraction(self.files, self.outputs(total="999.00", supplier_name=None))
        self.assertEqual(result["fields"]["total"]["wrong"], 1)              # only a.pdf was altered
        self.assertEqual(result["fields"]["supplier_name"]["missing"], 1)
        self.assertEqual(result["fully_correct_invoices"], 1)
        invented = self.outputs()
        invented["b.pdf"]["invoices"][0]["invoice_date"] = "2025-05-05"       # b.pdf has no date at all
        self.assertEqual(metrics.score_extraction(self.files, invented)["overall"]["spurious"], 1)

    def test_missed_invoice_counts_every_existing_field_as_missing(self):
        outputs = self.outputs()
        outputs["a.pdf"]["invoices"] = []
        result = metrics.score_extraction(self.files, outputs)
        self.assertEqual(result["invoice_detection"]["missed"], 1)
        self.assertEqual(result["fields"]["total"]["missing"], 1)
        self.assertEqual(result["errors"][0]["outcome"], "missed")

    def test_validation_detection_and_false_alarms(self):
        clean = metrics.score_validation(self.files, self.outputs())
        self.assertEqual((clean["detected_total"], clean["expected_total"]), (1, 1))
        self.assertEqual(clean["clean_files_with_unexpected_alarm"], 0)
        # an alarm on a perfectly extracted file is a false alarm ...
        outputs = self.outputs()
        outputs["a.pdf"]["issue_codes"] = ["SUBTOTAL_MISMATCH"]
        self.assertEqual(metrics.score_validation(self.files, outputs)["clean_files_with_unexpected_alarm"], 1)
        # ... but an alarm on a badly extracted file is explained
        outputs = self.outputs(total="999.00")
        outputs["a.pdf"]["issue_codes"] = ["TOTAL_MISMATCH"]
        result = metrics.score_validation(self.files, outputs)
        self.assertEqual((result["clean_files_with_unexpected_alarm"], result["explained_alarms"]), (0, 1))
        # an injected problem that was not flagged is reported
        outputs = self.outputs()
        outputs["b.pdf"]["issue_codes"] = []
        self.assertEqual(metrics.score_validation(self.files, outputs)["missed"], [{"file": "b.pdf", "code": "MISSING_FIELD"}])

    def test_cross_check_scoring(self):
        pairs = [{"files": ["a", "b"], "invoice_number": "INV-1", "expected_outcome": "match", "type": "pdf_pdf"},
                 {"files": ["a", "c"], "invoice_number": "INV-1", "expected_outcome": "mismatch", "type": "pdf_excel"}]
        checks = [{"files": ["b", "a"], "invoices": {"inv1": "match"}}]
        result = metrics.score_cross_checks(pairs, checks)
        self.assertEqual((result["detected"], result["correct_outcome"]), (1, 1))
        self.assertEqual(result["rows"][1]["got"], "not detected")

    def test_search_scoring(self):
        queries = [{"type": "supplier", "query": "x", "relevant": ["a"]}, {"type": "supplier", "query": "y", "relevant": ["b"]}]
        result = metrics.score_search(queries, {"keyword": {0: ["a", "c"], 1: ["c", "b"]}})
        stats = result["keyword"]["supplier"]
        self.assertEqual((stats["hit_at_1"], stats["hit_at_5"], stats["mrr"]), (0.5, 1.0, 0.75))

    def test_performance_summary(self):
        files = [{"kind": "pdf", "status": "completed", "time_ms": 100, "pages": 2}, {"kind": "pdf", "status": "failed", "time_ms": 300, "pages": 1}]
        result = metrics.score_performance(files)
        self.assertEqual(result["by_kind"]["pdf"]["median_ms"], 200)
        self.assertEqual(result["failure_rate"], 0.5)


class GeneratorTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "data"
        cls.truth = generate(cls.out, seed=5, scale=0.2)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        super().tearDownClass()

    def test_every_file_exists_and_the_ground_truth_is_on_disk(self):
        for entry in self.truth["files"]:
            self.assertTrue((self.out / entry["file"]).exists(), entry["file"])
        self.assertEqual(json.loads((self.out / "ground_truth.json").read_text())["meta"]["files"], len(self.truth["files"]))

    def test_same_seed_gives_the_same_truth(self):
        with tempfile.TemporaryDirectory() as other:
            again = generate(Path(other) / "d", seed=5, scale=0.2)
        self.assertEqual(json.dumps(again["files"], sort_keys=True), json.dumps(self.truth["files"], sort_keys=True))
        with tempfile.TemporaryDirectory() as other:
            different = generate(Path(other) / "d", seed=6, scale=0.2)
        self.assertNotEqual(json.dumps(different["files"], sort_keys=True), json.dumps(self.truth["files"], sort_keys=True))

    def test_truth_amounts_are_consistent_unless_a_wrong_total_was_injected(self):
        for entry in self.truth["files"]:
            for inv in entry["invoices"]:
                gap = (Decimal(inv["total"]) - Decimal(inv["subtotal"]) - Decimal(inv["tax"])
                       - Decimal(inv["discount"] or "0"))
                if "TOTAL_MISMATCH" in entry["expected_codes"] and entry["kind"] != "digital_pdf":
                    continue
                if entry["expected_codes"] == ["TOTAL_MISMATCH"]:
                    self.assertNotEqual(gap, 0, entry["file"])
                elif not entry["expected_codes"]:
                    self.assertEqual(gap, 0, entry["file"])

    def test_every_kind_of_document_is_covered(self):
        kinds = {e["kind"] for e in self.truth["files"]}
        self.assertTrue({"digital_pdf", "scanned_pdf", "png_image", "jpg_image", "tiff_image", "xlsx_register", "csv_register"} <= kinds)
        codes = {c for e in self.truth["files"] for c in e["expected_codes"]}
        self.assertTrue({"TOTAL_MISMATCH", "MISSING_FIELD", "DUPLICATE_FILE", "DUPLICATE_INVOICE", "CROSS_CHECK_MISMATCH"} <= codes)
        self.assertTrue(self.truth["cross_pairs"] and self.truth["search_queries"])

    def test_digital_pdfs_contain_the_truth_in_their_text(self):
        for entry in self.truth["files"]:
            if entry["kind"] != "digital_pdf":
                continue
            text = "".join(page.get_text() for page in pymupdf.open(self.out / entry["file"]))
            for inv in entry["invoices"]:
                self.assertIn(inv["invoice_number"], text, entry["file"])
                self.assertIn(inv["supplier_name"].lower(), text.lower(), entry["file"])     # letterheads are upper-case

    def test_missing_date_invoices_really_have_no_date(self):
        for entry in self.truth["files"]:
            if entry["expected_codes"] == ["MISSING_FIELD"]:
                self.assertIsNone(entry["invoices"][0]["invoice_date"])
                text = "".join(p.get_text() for p in pymupdf.open(self.out / entry["file"]))
                self.assertNotIn("Date", text.replace("Invoice Date", "Invoice Date"))

    def test_duplicate_copy_is_byte_identical(self):
        pairs = [e for e in self.truth["files"] if "DUPLICATE_FILE" in e["expected_codes"]]
        self.assertTrue(pairs)
        copy = pairs[0]["file"]
        names = {e["file"] for e in self.truth["files"]}
        original = next(n for n in names if n.endswith("dup_original.pdf") and int(n[:3]) == int(copy[:3]) - 1)
        self.assertEqual((self.out / copy).read_bytes(), (self.out / original).read_bytes())

    def test_stress_pdf_has_the_requested_pages(self):
        path = self.out / "stress.pdf"
        invoices = generate_stress_pdf(path, pages=20, pages_per_invoice=5)
        self.assertEqual(invoices, 4)
        self.assertEqual(len(pymupdf.open(path)), 20)

    def test_money_rounding(self):
        self.assertEqual(q2(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(Factory(1).invoice().total, q2(Factory(1).invoice().total))


class ReportTests(SimpleTestCase):
    def test_report_contains_the_measured_numbers_and_flags_the_fallback_embedder(self):
        fields = {f: {"correct": 9, "wrong": 1, "missing": 0, "spurious": 0, "precision": 0.9, "recall": 0.9, "f1": 0.9} for f in metrics.FIELDS}
        overall = {"correct": 72, "wrong": 8, "missing": 0, "spurious": 0, "precision": 0.9, "recall": 0.9, "f1": 0.9,
                   "hallucination_rate": 0.1, "field_accuracy": 0.9}
        result = {
            "run": {"date": "d", "mode": "rule-based (no LLM)", "embedder": "hashing-384", "python": "3", "platform": "p", "cpus": 2,
                    "dataset": {"files": 1, "invoices": 10, "seed": 1, "scale": 1.0}},
            "extraction": {"fields": fields, "overall": overall, "by_condition": {"digital": {"invoices": 10, "fully_correct": 5, **overall}},
                           "invoice_detection": {"truth": 10, "found": 10, "missed": 0, "extra": 0, "recall": 1.0, "precision": 1.0},
                           "fully_correct_invoices": 5, "invoices_scored": 10, "line_item_count_accuracy": 0.5, "line_item_invoices": 10, "errors": []},
            "validation": {"per_code": {"TOTAL_MISMATCH": {"expected": 2, "detected": 1}}, "detection_rate": 0.5, "expected_total": 2, "detected_total": 1,
                           "clean_files": 5, "clean_files_with_unexpected_alarm": 1, "false_alarm_rate": 0.2, "unexpected_codes": {"X": 1},
                           "explained_alarms": 3, "missed": [{"file": "a.pdf", "code": "TOTAL_MISMATCH"}]},
            "cross_checks": {"pairs": 2, "detected": 2, "correct_outcome": 1, "accuracy": 0.5,
                             "rows": [{"type": "pdf_pdf", "invoice": "I1", "expected": "match", "got": "mismatch"}]},
            "search": {"keyword": {"all": {"queries": 4, "hit_at_1": 0.5, "hit_at_5": 0.75, "mrr": 0.6}}},
            "search_queries": {"supplier": 4},
            "performance": {"by_kind": {"digital_pdf": {"files": 1, "pages": 1, "median_ms": 20, "p95_ms": 20, "total_s": 0.02, "failed": 0}},
                            "statuses": {"completed": 1}, "failure_rate": 0.0},
            "stress": {"pages": 1000, "size_mb": 10.0, "invoices_expected": 200, "invoices_found": 200, "status": "completed", "llm": False,
                       "seconds": 12.0, "pages_per_second": 83.3, "peak_memory_mb": 170.0},
            "ocr_confidence": {"files": 1, "mean": 0.8, "min": 0.8},
        }
        text = build_report(result)
        for expected in ("precision 90.0%", "Detected **1 of 2**", "TOTAL_MISMATCH", "83.3 pages/s",
                         "offline fallback", "a.pdf", "Hit@k"):
            self.assertIn(expected, text)
        result["run"]["embedder"] = "BAAI/bge-small-en-v1.5"
        self.assertNotIn("offline fallback", build_report(result))


class CommandTests(SimpleTestCase):
    def test_generate_command(self):
        with tempfile.TemporaryDirectory() as folder:
            out = StringIO()
            call_command("generate_eval_dataset", "--out", str(Path(folder) / "d"), "--scale", "0.1", stdout=out)
            self.assertIn("Created", out.getvalue())
            self.assertTrue((Path(folder) / "d" / "ground_truth.json").exists())
