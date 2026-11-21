"""Run the real pipeline over a generated dataset and score it."""
import json
import os
import platform
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

from . import metrics, resource_usage
from .generator import generate_stress_pdf


def _environment(use_llm_label: str) -> dict:
    from documents.search.embeddings import get_embedder

    return {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "mode": use_llm_label,
            "embedder": get_embedder().name, "python": platform.python_version(), "platform": platform.platform(),
            "cpus": os.cpu_count()}


def run_stress(pages: int, use_llm: bool, progress=print) -> dict:
    """One large PDF made of many multi-page invoices. Measures time and peak memory."""
    from documents.orchestrator import process_document
    from documents.processing import create_document_from_path

    workdir = Path(tempfile.mkdtemp(prefix="docintel-stress-"))
    try:
        path = workdir / "stress.pdf"
        expected = generate_stress_pdf(path, pages=pages)
        size_mb = path.stat().st_size / 1_048_576
        progress(f"Stress test: {pages} pages / {expected} invoices ({size_mb:.1f} MB)...")
        owner = get_user_model().objects.get_or_create(username="evaluator")[0]
        started = time.perf_counter()
        document = create_document_from_path(path, owner=owner)
        kwargs = {} if use_llm else {"llm": None}
        process_document(document, **kwargs)
        elapsed = time.perf_counter() - started
        document.refresh_from_db()
        found = document.results.count()
        return {"pages": pages, "invoices_expected": expected, "invoices_found": found, "size_mb": round(size_mb, 1),
                "status": document.status, "pages_processed": document.pages_processed, "seconds": round(elapsed, 1),
                "pages_per_second": round(pages / elapsed, 1) if elapsed else None,
                "peak_memory_mb": resource_usage.peak_memory_mb(), "llm": use_llm, "error": document.error_message}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_evaluation(data_dir: Path, use_llm: bool = True, stress_pages: int = 0, stress_llm: bool = False,
                   progress=print) -> dict:
    """Process every file in ``data_dir`` through the real pipeline (in a throw-away database) and score it."""
    from documents.extraction.llm import get_llm_client
    from documents.models import CrossVerification, Document
    from documents.orchestrator import process_document
    from documents.processing import ProcessingError, create_document_from_path
    from documents.search import query as search_query
    from documents.models import SearchChunk

    truth = json.loads((data_dir / "ground_truth.json").read_text(encoding="utf-8"))
    client = get_llm_client() if use_llm else None
    mode = f"LLM ({settings.GROQ_MODEL})" if client else "rule-based (no LLM)"
    if use_llm and client is None:
        progress("No LLM configured (GROQ_API_KEY / GROQ_MODEL): running rule-based extraction.")

    runner = DiscoverRunner(verbosity=0, interactive=False)
    old_config = runner.setup_databases()
    media = tempfile.mkdtemp(prefix="docintel-eval-media-")
    try:
        with override_settings(MEDIA_ROOT=media):
            stress = run_stress(stress_pages, stress_llm, progress) if stress_pages else None
            if stress:
                Document.objects.all().delete()
            owner = get_user_model().objects.get_or_create(username="evaluator")[0]
            documents: dict[str, Document] = {}
            seen_hashes: dict[str, str] = {}
            for index, entry in enumerate(truth["files"], start=1):
                path = data_dir / entry["file"]
                progress(f"[{index}/{len(truth['files'])}] {entry['file']}")
                try:
                    document = create_document_from_path(path, owner=owner)
                except ProcessingError as exc:
                    documents[entry["file"]] = exc
                    continue
                kwargs = {} if use_llm else {"llm": None}
                process_document(document, **kwargs)
                documents[entry["file"]] = document

            outputs: dict[str, dict] = {}
            perf_files = []
            name_of = {}
            for entry in truth["files"]:
                document = documents[entry["file"]]
                if isinstance(document, Exception):
                    outputs[entry["file"]] = {"status": "rejected", "invoices": [], "issue_codes": []}
                    perf_files.append({"kind": entry["kind"], "status": "failed", "time_ms": None, "pages": 0})
                    continue
                document.refresh_from_db()
                name_of[document.pk] = entry["file"]
                invoices = []
                for result in document.results.prefetch_related("line_items").order_by("page_start", "id"):
                    invoices.append({
                        "invoice_number": result.invoice_number, "invoice_date": result.invoice_date.isoformat() if result.invoice_date else None,
                        "supplier_name": result.supplier_name, "customer_name": result.customer_name, "currency": result.currency,
                        "subtotal": str(result.subtotal) if result.subtotal is not None else None,
                        "discount": str(result.discount) if result.discount is not None else None,
                        "tax": str(result.tax) if result.tax is not None else None,
                        "total": str(result.total) if result.total is not None else None,
                        "item_count": result.line_items.count(), "method": result.method})
                codes = sorted(set(document.issues.filter(severity__in=("error", "warning")).values_list("code", flat=True)))
                confidences = [p.ocr_confidence for p in document.pages.all() if p.ocr_confidence]
                outputs[entry["file"]] = {"status": document.status, "invoices": invoices, "issue_codes": codes,
                                          "ocr_confidence": sum(confidences) / len(confidences) if confidences else None}
                perf_files.append({"kind": entry["kind"], "status": document.status, "time_ms": document.processing_time_ms,
                                   "pages": document.page_count})

            checks = []
            for check in CrossVerification.objects.all():
                invoices = {metrics.alnum(i["invoice_number"]): i["outcome"] for i in check.details.get("invoices", [])}
                checks.append({"files": [name_of.get(check.document_a_id), name_of.get(check.document_b_id)], "invoices": invoices})

            progress("Scoring search...")
            queries = truth["search_queries"]
            rankings: dict[str, dict[int, list[str]]] = {"keyword": {}, "semantic": {}, "hybrid": {}}
            base = SearchChunk.objects.filter(document__owner=owner)
            for position, item in enumerate(queries):
                for mode_name in rankings:
                    outcome = search_query.search(base, item["query"], mode_name, 10, {})
                    ranked = []
                    for hit in outcome["hits"]:
                        name = name_of.get(hit.chunk.document_id)
                        if name and name not in ranked:
                            ranked.append(name)
                    rankings[mode_name][position] = ranked
            from documents.search.embeddings import get_embedder
            embedder_name = get_embedder().name

        result = {
            "run": {**_environment(mode), "embedder": embedder_name, "dataset": truth["meta"], "stress_llm": stress_llm},
            "extraction": metrics.score_extraction(truth["files"], outputs),
            "validation": metrics.score_validation(truth["files"], outputs),
            "cross_checks": metrics.score_cross_checks(truth["cross_pairs"], checks),
            "search": metrics.score_search(queries, rankings),
            "search_queries": {t: sum(1 for q in queries if q["type"] == t) for t in sorted({q["type"] for q in queries})},
            "performance": metrics.score_performance(perf_files),
            "stress": stress,
            "files": outputs,
            "ocr_confidence": _ocr_summary(truth["files"], outputs),
        }
        return result
    finally:
        runner.teardown_databases(old_config)
        shutil.rmtree(media, ignore_errors=True)


def _ocr_summary(files: list[dict], outputs: dict[str, dict]) -> dict:
    values = [outputs[f["file"]]["ocr_confidence"] for f in files if outputs.get(f["file"], {}).get("ocr_confidence")]
    return {"files": len(values), "mean": sum(values) / len(values) if values else None, "min": min(values) if values else None}
