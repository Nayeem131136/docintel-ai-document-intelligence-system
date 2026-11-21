"""Turn evaluation results into a Markdown report. Every number comes from the results dictionary."""
from .metrics import FIELDS

LABELS = {"invoice_number": "Invoice number", "invoice_date": "Invoice date", "supplier_name": "Supplier",
          "customer_name": "Customer", "currency": "Currency", "subtotal": "Subtotal", "discount": "Discount", "tax": "Tax", "total": "Total"}
CONDITIONS = {"digital": "Digital PDF", "scan": "Scanned PDF / PNG / TIFF", "photo": "Photographed JPG", "sheet": "Excel / CSV register"}
SEARCH_TYPES = {"invoice_number": "Invoice number", "supplier": "Supplier name", "item_paraphrase": "Product described in other words", "all": "All queries"}


def pct(value, digits=1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def num(value, digits=1) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def build_report(result: dict) -> str:
    run, ex, val, cross = result["run"], result["extraction"], result["validation"], result["cross_checks"]
    search, perf, stress = result["search"], result["performance"], result.get("stress")
    meta = run["dataset"]
    lines: list[str] = []
    add = lines.append

    add("# Evaluation Report")
    add("")
    add("All numbers in this report were produced by `python manage.py run_evaluation` on the run described below. "
        "Nothing is estimated or typed in by hand; the same command regenerates the whole file.")
    add("")
    add("## 1. Run details")
    add("")
    add(table(["Item", "Value"], [
        ["Date", run["date"]], ["Extraction mode", run["mode"]], ["Embedding model (semantic search)", run["embedder"]],
        ["Dataset", f"{meta['files']} files, {meta['invoices']} invoices (seed {meta['seed']}, scale {meta['scale']})"],
        ["Machine", f"{run['platform']}, {run['cpus']} CPU threads, Python {run['python']}"],
    ]))
    add("")
    if run["mode"].startswith("rule-based"):
        add("> This run used the **rule-based fallback only** (what the app does when no LLM is configured). "
            "To measure the LLM path, put `GROQ_API_KEY` and `GROQ_MODEL` in `.env` and run the command in section 9 without `--no-llm`.")
        add("")
    add("**Dataset.** Synthetic invoices of fictional companies in three different layouts, rendered as digital PDFs, "
        "multi-invoice PDFs, long multi-page invoices, scanned PDFs, PNG/JPG images (rotated, blurred, noisy; the JPGs are "
        "smaller and unevenly lit to imitate phone photos), a multi-page TIFF, and XLSX / XLS / CSV registers with different "
        "header names. Money is written as `1,234.50`, `1.234,50` or with `€`/`£`; dates in four formats. Problems with a "
        "known expected outcome were injected: wrong printed totals, missing dates, identical files uploaded twice, the same "
        "invoice in two documents, and PDF-vs-Excel pairs with and without a differing total. The exact answer for every "
        "field is stored in `ground_truth.json` (exact by construction).")
    add("")

    add("## 2. Field extraction")
    add("")
    o = ex["overall"]
    add(f"Across {ex['invoices_scored']} invoices: **precision {pct(o['precision'])}**, **recall {pct(o['recall'])}**, "
        f"**F1 {pct(o['f1'])}**. {ex['fully_correct_invoices']} invoices ({pct(ex['fully_correct_invoices'] / max(1, ex['invoices_scored']))}) "
        f"had every field right. Invented values (the system filled in something wrong or where nothing exists): "
        f"**{pct(o['hallucination_rate'], 2)}** of the values it returned ({o['wrong']} wrong, {o['spurious']} where the document has no value).")
    add("")
    add("*Definitions.* Correct = equals the ground truth (names and numbers compared ignoring case and punctuation, "
        "amounts within 0.01, dates exactly). Precision = correct / values returned. Recall = correct / values that exist "
        "in the document. A value left empty counts against recall but not precision, because the system is designed to "
        "leave a field empty instead of guessing.")
    add("")
    add(table(["Field", "Correct", "Wrong", "Not found", "Precision", "Recall", "F1"],
              [[LABELS[f], ex["fields"][f]["correct"], ex["fields"][f]["wrong"], ex["fields"][f]["missing"],
                pct(ex["fields"][f]["precision"]), pct(ex["fields"][f]["recall"]), pct(ex["fields"][f]["f1"])] for f in FIELDS]))
    add("")
    add("### By document type")
    add("")
    add(table(["Type", "Invoices", "Fully correct", "Precision", "Recall"],
              [[CONDITIONS.get(c, c), v["invoices"], f"{v['fully_correct']} ({pct(v['fully_correct'] / max(1, v['invoices']), 0)})",
                pct(v["precision"]), pct(v["recall"])] for c, v in ex["by_condition"].items()]))
    add("")
    d = ex["invoice_detection"]
    add(f"**Invoice detection:** found {d['found']} of {d['truth']} invoices (recall {pct(d['recall'])}); "
        f"{d['extra']} extra invoice(s) that do not exist (precision {pct(d['precision'])}). "
        f"Line-item count matched exactly for {pct(ex['line_item_count_accuracy'])} of the {ex['line_item_invoices']} invoices that have an item table.")
    ocr = result.get("ocr_confidence") or {}
    if ocr.get("files"):
        add("")
        add(f"**OCR:** mean engine confidence {pct(ocr['mean'])} over {ocr['files']} scanned / photographed files (lowest {pct(ocr['min'])}).")
    add("")

    add("## 3. Validation and review flags")
    add("")
    add(f"Detected **{val['detected_total']} of {val['expected_total']}** injected problems ({pct(val['detection_rate'])}).")
    add("")
    add(table(["Problem", "Injected", "Detected"], [[c, v["expected"], v["detected"]] for c, v in val["per_code"].items()]))
    add("")
    add(f"False alarms: of {val['clean_files']} files with no injected problem, {val['clean_files_with_unexpected_alarm']} "
        f"raised an alarm although their extraction was fully correct (**{pct(val['false_alarm_rate'])}**). "
        f"A further {val['explained_alarms']} alarm(s) appeared on files whose extraction was itself wrong or incomplete; "
        "those are the validator correctly pointing at a real problem (for example a missing supplier), so they are not counted as false alarms.")
    if val["unexpected_codes"]:
        add("")
        add("Unexplained alarms by code: " + ", ".join(f"{c} x{n}" for c, n in val["unexpected_codes"].items()) + ".")
    if val["missed"]:
        add("")
        add("Injected problems that were **not** detected:")
        add("")
        add(table(["File", "Expected flag"], [[m["file"], m["code"]] for m in val["missed"]]))
    add("")

    add("## 4. Cross-verification (PDF vs PDF, PDF vs Excel)")
    add("")
    add(f"{cross['pairs']} invoice pairs: the comparison was found for {cross['detected']}, and the outcome (match / mismatch) was right for "
        f"**{cross['correct_outcome']}** ({pct(cross['accuracy'])}).")
    wrong_pairs = [r for r in cross["rows"] if r["expected"] != r["got"]]
    if wrong_pairs:
        add("")
        add(table(["Type", "Invoice", "Expected", "Got"], [[r["type"], r["invoice"], r["expected"], r["got"]] for r in wrong_pairs]))
    add("")

    add("## 5. Search")
    add("")
    counts = result["search_queries"]
    add(f"Queries were generated from the ground truth: {', '.join(f'{n} by {SEARCH_TYPES[t].lower()}' for t, n in counts.items())}. "
        "A result counts as relevant when it is a document that contains the invoice / supplier / product. "
        f"Semantic and hybrid modes used the **{run['embedder']}** embedder."
        + (" This is the built-in offline fallback, which matches words and spellings but not meaning, so the semantic numbers below "
           "understate what the real model achieves; re-run on a machine that can download the model."
           if run["embedder"].startswith("hashing") else ""))
    add("")
    rows = []
    for group in ("invoice_number", "supplier", "item_paraphrase", "all"):
        for mode in ("keyword", "semantic", "hybrid"):
            v = search.get(mode, {}).get(group)
            if v:
                rows.append([SEARCH_TYPES[group], mode, v["queries"], pct(v["hit_at_1"]), pct(v["hit_at_5"]), f"{v['mrr']:.3f}"])
    add(table(["Query type", "Mode", "Queries", "Hit@1", "Hit@5", "MRR"], rows))
    add("")
    add("*Hit@k* = a relevant document is among the first k results. *MRR* = mean of 1 / rank of the first relevant result.")
    add("")

    add("## 6. Performance")
    add("")
    add(table(["File type", "Files", "Pages", "Median per file", "Slowest 5%", "Total", "Failed"],
              [[k, v["files"], v["pages"], f"{num(v['median_ms'], 0)} ms", f"{num(v['p95_ms'], 0)} ms", f"{num(v['total_s'])} s", v["failed"]]
               for k, v in perf["by_kind"].items()]))
    add("")
    add(f"Processing outcome: {', '.join(f'{k} {n}' for k, n in perf['statuses'].items())}. Failure rate {pct(perf['failure_rate'])}.")
    if stress:
        add("")
        add("### Large document")
        add("")
        add(table(["Item", "Value"], [
            ["Document", f"{stress['pages']} pages, {stress['size_mb']} MB, {stress['invoices_expected']} invoices"],
            ["Extraction", "LLM" if stress["llm"] else "rule-based (LLM off: a 1000-page file would otherwise make one API call per invoice)"],
            ["Result", f"{stress['status']}, {stress['invoices_found']} of {stress['invoices_expected']} invoices found"],
            ["Total time", f"{stress['seconds']} s ({stress['pages_per_second']} pages/s)"],
            ["Peak memory of the whole run", f"{stress['peak_memory_mb']} MB" if stress["peak_memory_mb"] else "not measured on this OS"],
        ]))
    add("")

    add("## 7. Examples of mistakes")
    add("")
    if ex["errors"]:
        add(table(["File", "Field", "Problem", "Expected", "Got"], [[e["file"], e["field"], e["outcome"], e["expected"], e["got"]] for e in ex["errors"][:20]]))
    else:
        add("No field errors in this run.")
    add("")

    add("## 8. Limitations of this evaluation")
    add("")
    add("- The data is synthetic: three clean layouts and a fixed vocabulary. Real invoices are messier, so real-world accuracy can be lower, especially for scans. "
        "Treat these numbers as a reproducible benchmark of this system, not as a promise about every invoice.")
    add("- Scans and photos are simulated (rotation, blur, noise, lighting, lower resolution), not real camera images.")
    add("- One run on one machine; timings depend on the CPU, and LLM mode also depends on network latency and API limits.")
    add("- Semantic search quality depends on the embedding model; see the embedder named in section 1.")
    add("- Search queries were generated from the same ground truth; the product paraphrases were written by hand (12 products, 2 each).")
    add("")
    add("## 9. Reproduce")
    add("")
    add("```bash")
    add("cd backend")
    add("python manage.py generate_eval_dataset --out eval_data --seed 42")
    add("python manage.py run_evaluation --data eval_data --stress-pages 1000 --report ../docs/EVALUATION_REPORT.md")
    add("python manage.py run_evaluation --data eval_data --no-llm            # rule-based fallback only, for comparison")
    add("```")
    add("")
    return "\n".join(lines)
