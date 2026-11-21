"""Scoring functions. Pure Python (no database), so they can be unit-tested and reused."""
import re
import statistics
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name", "currency", "subtotal", "discount", "tax", "total"]
MONEY = {"subtotal", "discount", "tax", "total"}
TOLERANCE = Decimal("0.01")


def alnum(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def values_equal(field: str, truth, predicted) -> bool:
    if field in MONEY:
        a, b = _decimal(truth), _decimal(predicted)
        return a is not None and b is not None and abs(a - b) <= TOLERANCE
    if field == "currency":
        return str(truth or "").upper() == str(predicted or "").upper()
    if field == "invoice_date":
        return str(truth or "") == str(predicted or "")
    return alnum(truth) == alnum(predicted)


def compare_field(field: str, truth, predicted) -> str:
    """correct | wrong | missing (value exists but was not found) | spurious (invented where nothing exists) | empty."""
    has_truth = truth not in (None, "")
    has_pred = predicted not in (None, "")
    if has_truth and has_pred:
        return "correct" if values_equal(field, truth, predicted) else "wrong"
    if has_truth:
        return "missing"
    return "spurious" if has_pred else "empty"


def match_invoices(truths: list[dict], predictions: list[dict]):
    """Pair predicted invoices with ground-truth invoices of the same file.

    First by invoice number; the leftovers are paired in reading order, so a misread number is scored as a
    wrong field instead of as one missed plus one extra invoice. Returns (pairs, missed, extra).
    """
    unmatched_pred = list(range(len(predictions)))
    pairs: list[tuple[dict, dict]] = []
    leftover_truth = []
    for truth in truths:
        found = next((i for i in unmatched_pred if alnum(predictions[i].get("invoice_number")) == alnum(truth["invoice_number"])
                      and alnum(truth["invoice_number"])), None)
        if found is None:
            leftover_truth.append(truth)
        else:
            unmatched_pred.remove(found)
            pairs.append((truth, predictions[found]))
    while leftover_truth and unmatched_pred:
        pairs.append((leftover_truth.pop(0), predictions[unmatched_pred.pop(0)]))
    return pairs, leftover_truth, [predictions[i] for i in unmatched_pred]


def prf(correct: int, wrong: int, missing: int) -> dict:
    """Precision = correct / filled-in values; recall = correct / values that exist; F1 = harmonic mean."""
    precision = correct / (correct + wrong) if correct + wrong else None
    recall = correct / (correct + wrong + missing) if correct + wrong + missing else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if precision == 0 or recall == 0 else None)
    return {"precision": precision, "recall": recall, "f1": f1}


def percentile(values: list[float], q: float):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def reciprocal_rank(ranked_files: list[str], relevant: set[str]):
    for position, name in enumerate(ranked_files, start=1):
        if name in relevant:
            return 1 / position
    return 0.0


def score_extraction(truth_files: list[dict], outputs: dict[str, dict], error_limit: int = 30) -> dict:
    """Field-level accuracy overall and by condition, invoice detection and a sample of the mistakes."""
    fields = {f: Counter() for f in FIELDS}
    by_condition: dict[str, dict[str, Counter]] = defaultdict(lambda: {f: Counter() for f in FIELDS})
    detection = Counter()
    fully_correct = Counter()                 # per condition: invoices with every field right
    totals = Counter()
    items = Counter()
    errors: list[dict] = []

    for entry in truth_files:
        out = outputs.get(entry["file"], {})
        condition = entry["condition"]
        pairs, missed, extra = match_invoices(entry["invoices"], out.get("invoices", []))
        detection["truth"] += len(entry["invoices"])
        detection["found"] += len(pairs)
        detection["missed"] += len(missed)
        detection["extra"] += len(extra)
        for truth, pred in pairs:
            outcomes = {}
            for field in FIELDS:
                outcome = compare_field(field, truth.get(field), pred.get(field))
                outcomes[field] = outcome
                fields[field][outcome] += 1
                by_condition[condition][field][outcome] += 1
                if outcome in ("wrong", "missing", "spurious") and len(errors) < error_limit:
                    errors.append({"file": entry["file"], "field": field, "outcome": outcome,
                                   "expected": truth.get(field), "got": pred.get(field)})
            totals[condition] += 1
            if all(o in ("correct", "empty") for o in outcomes.values()):
                fully_correct[condition] += 1
            if entry["kind"] not in ("xlsx_register", "xls_register", "csv_register") and truth["item_count"]:
                items["total"] += 1
                items["correct"] += int(pred.get("item_count") == truth["item_count"])
        for truth in missed:
            for field in FIELDS:
                outcome = "missing" if truth.get(field) not in (None, "") else "empty"
                fields[field][outcome] += 1
                by_condition[condition][field][outcome] += 1
            totals[condition] += 1
            if len(errors) < error_limit:
                errors.append({"file": entry["file"], "field": "(whole invoice)", "outcome": "missed",
                               "expected": truth["invoice_number"], "got": None})

    def summarise(counter: Counter) -> dict:
        return {"correct": counter["correct"], "wrong": counter["wrong"], "missing": counter["missing"],
                "spurious": counter["spurious"], **prf(counter["correct"], counter["wrong"], counter["missing"])}

    overall = Counter()
    for counter in fields.values():
        overall.update(counter)
    condition_summary = {}
    for condition, table in by_condition.items():
        merged = Counter()
        for counter in table.values():
            merged.update(counter)
        condition_summary[condition] = {"invoices": totals[condition], "fully_correct": fully_correct[condition],
                                        "field_accuracy": (merged["correct"] + merged["empty"]) / max(1, sum(merged.values())),
                                        **summarise(merged)}
    predicted_values = overall["correct"] + overall["wrong"] + overall["spurious"]
    return {
        "fields": {f: summarise(c) for f, c in fields.items()},
        "overall": {**summarise(overall), "hallucination_rate": (overall["wrong"] + overall["spurious"]) / predicted_values if predicted_values else None,
                    "spurious": overall["spurious"],
                    "field_accuracy": (overall["correct"] + overall["empty"]) / max(1, sum(overall.values()))},
        "by_condition": condition_summary,
        "invoice_detection": {"truth": detection["truth"], "found": detection["found"], "missed": detection["missed"], "extra": detection["extra"],
                              "recall": detection["found"] / detection["truth"] if detection["truth"] else None,
                              "precision": detection["found"] / (detection["found"] + detection["extra"]) if detection["found"] + detection["extra"] else None},
        "fully_correct_invoices": sum(fully_correct.values()), "invoices_scored": sum(totals.values()),
        "line_item_count_accuracy": items["correct"] / items["total"] if items["total"] else None, "line_item_invoices": items["total"],
        "errors": errors,
    }


def files_with_extraction_errors(truth_files: list[dict], outputs: dict[str, dict]) -> set[str]:
    """Files where at least one invoice was missed or has a wrong / missing / invented field or item count."""
    bad = set()
    for entry in truth_files:
        pairs, missed, extra = match_invoices(entry["invoices"], outputs.get(entry["file"], {}).get("invoices", []))
        if missed or extra:
            bad.add(entry["file"])
        for truth, pred in pairs:
            if any(compare_field(f, truth.get(f), pred.get(f)) in ("wrong", "missing", "spurious") for f in FIELDS):
                bad.add(entry["file"])
            if entry["kind"] not in ("xlsx_register", "xls_register", "csv_register") and truth["item_count"] \
                    and pred.get("item_count") != truth["item_count"]:
                bad.add(entry["file"])
    return bad


def score_validation(truth_files: list[dict], outputs: dict[str, dict]) -> dict:
    """Detection rate of injected problems, and false alarms.

    An alarm on a file whose extraction was itself wrong or incomplete (e.g. MISSING_FIELD for a supplier the
    extractor did not find) is *explained*: the validator correctly flagged a real problem. Only alarms on files
    whose extraction was fully correct count as false alarms.
    """
    explained_files = files_with_extraction_errors(truth_files, outputs)
    explained_alarms = 0
    expected_total = Counter()
    expected_hit = Counter()
    clean_files = clean_with_alarm = 0
    unexpected = Counter()
    missed: list[dict] = []
    for entry in truth_files:
        raised = set(outputs.get(entry["file"], {}).get("issue_codes", []))
        expected = set(entry["expected_codes"])
        for code in expected:
            expected_total[code] += 1
            if code in raised:
                expected_hit[code] += 1
            else:
                missed.append({"file": entry["file"], "code": code})
        extra = raised - expected - set(entry["allowed_codes"])
        if extra and entry["file"] in explained_files:
            explained_alarms += len(extra)
            extra = set()
        if not expected:
            clean_files += 1
            clean_with_alarm += bool(extra)
        for code in extra:
            unexpected[code] += 1
    total = sum(expected_total.values())
    hit = sum(expected_hit.values())
    return {
        "per_code": {c: {"expected": expected_total[c], "detected": expected_hit[c]} for c in sorted(expected_total)},
        "detection_rate": hit / total if total else None, "expected_total": total, "detected_total": hit,
        "clean_files": clean_files, "clean_files_with_unexpected_alarm": clean_with_alarm,
        "false_alarm_rate": clean_with_alarm / clean_files if clean_files else None,
        "unexpected_codes": dict(unexpected.most_common()), "explained_alarms": explained_alarms, "missed": missed,
    }


def score_cross_checks(pairs: list[dict], checks: list[dict]) -> dict:
    """``checks``: [{files:[a,b], invoices:{normalised number: outcome}}]"""
    rows, correct, found = [], 0, 0
    for pair in pairs:
        a, b = pair["files"]
        match = next((c for c in checks if set(c["files"]) == {a, b}), None)
        outcome = (match or {}).get("invoices", {}).get(alnum(pair["invoice_number"])) if match else None
        found += outcome is not None
        ok = outcome == pair["expected_outcome"]
        correct += ok
        rows.append({"type": pair["type"], "invoice": pair["invoice_number"], "expected": pair["expected_outcome"], "got": outcome or "not detected"})
    return {"pairs": len(pairs), "detected": found, "correct_outcome": correct,
            "accuracy": correct / len(pairs) if pairs else None, "rows": rows}


def score_search(queries: list[dict], rankings: dict[str, dict[int, list[str]]]) -> dict:
    """``rankings[mode][query index]`` = ranked file names."""
    result: dict = {}
    for mode, per_query in rankings.items():
        groups: dict[str, list] = defaultdict(list)
        for index, ranked in per_query.items():
            relevant = set(queries[index]["relevant"])
            rr = reciprocal_rank(ranked, relevant)
            groups[queries[index]["type"]].append((rr, bool(ranked[:1]) and ranked[0] in relevant, any(f in relevant for f in ranked[:5])))
            groups["all"].append(groups[queries[index]["type"]][-1])
        result[mode] = {g: {"queries": len(v), "hit_at_1": sum(x[1] for x in v) / len(v), "hit_at_5": sum(x[2] for x in v) / len(v),
                            "mrr": sum(x[0] for x in v) / len(v)} for g, v in groups.items()}
    return result


def score_performance(files: list[dict]) -> dict:
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for entry in files:
        by_kind[entry["kind"]].append(entry)
    table = {}
    for kind, entries in sorted(by_kind.items()):
        times = [e["time_ms"] for e in entries if e.get("time_ms") is not None]
        pages = sum(e.get("pages") or 0 for e in entries)
        table[kind] = {"files": len(entries), "pages": pages, "median_ms": statistics.median(times) if times else None,
                       "p95_ms": percentile(times, 0.95), "total_s": sum(times) / 1000,
                       "failed": sum(e["status"] == "failed" for e in entries)}
    statuses = Counter(e["status"] for e in files)
    return {"by_kind": table, "statuses": dict(statuses), "failure_rate": statuses["failed"] / len(files) if files else None}
