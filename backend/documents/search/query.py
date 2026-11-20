"""Keyword, semantic and hybrid search over a user's own documents."""
import re
from dataclasses import dataclass
from datetime import date

import numpy as np
from django.conf import settings
from django.db.models import Q

from ..models import SearchChunk
from .embeddings import embed_texts, from_bytes

TOKEN_RE = re.compile(r"[\w][\w\-./#]*", re.UNICODE)
RRF_K = 60


@dataclass
class Hit:
    chunk: SearchChunk
    score: float
    keyword_score: float | None = None
    semantic_score: float | None = None


def tokenize(query: str) -> list[str]:
    seen, tokens = set(), []
    for token in TOKEN_RE.findall(query.lower()):
        token = token.strip("-./#")
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens[:12]


def apply_filters(queryset, filters: dict):
    """Filters on the invoice fields restrict the search to invoice chunks."""
    if filters.get("kind"):
        queryset = queryset.filter(kind=filters["kind"])
    if filters.get("document"):
        queryset = queryset.filter(document_id=filters["document"])
    if filters.get("file_type"):
        queryset = queryset.filter(document__file_type=filters["file_type"])
    invoice_filters = {
        "supplier": "result__supplier_name__icontains", "customer": "result__customer_name__icontains",
        "currency": "result__currency__iexact", "review_status": "result__review_status",
        "date_from": "result__invoice_date__gte", "date_to": "result__invoice_date__lte",
        "min_total": "result__total__gte", "max_total": "result__total__lte",
    }
    used = {key: value for key, value in filters.items() if key in invoice_filters and value not in (None, "")}
    if used:
        queryset = queryset.filter(result__isnull=False, **{invoice_filters[k]: v for k, v in used.items()})
    return queryset


def keyword_search(base, query: str, limit: int) -> list[Hit]:
    """Every word must appear (case-insensitive). Ranked by how often, with a boost for invoice
    records and for exact invoice-number matches."""
    tokens = tokenize(query)
    if not tokens:
        return []
    queryset = base
    for token in tokens:
        queryset = queryset.filter(Q(text__icontains=token))
    hits = []
    for chunk in queryset.select_related("result", "document")[:2000]:
        lowered = chunk.text.lower()
        score = sum(min(lowered.count(token), 5) for token in tokens) / len(tokens)
        if chunk.kind == SearchChunk.Kind.INVOICE:
            score += 3
            number = (chunk.result.invoice_number or "").lower() if chunk.result else ""
            if number and number in tokens:
                score += 5
        hits.append(Hit(chunk, score, keyword_score=score))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def semantic_search(base, query: str, limit: int) -> tuple[list[Hit], str]:
    vectors, model_name = embed_texts([query])
    candidates = list(base.filter(embedding_model=model_name, embedding__isnull=False)
                      .select_related("result", "document")[:settings.SEMANTIC_MAX_CANDIDATES])
    if not candidates:
        return [], model_name
    matrix = np.vstack([from_bytes(c.embedding) for c in candidates])
    scores = matrix @ vectors[0]
    order = np.argsort(-scores)[:limit * 3]
    floor = settings.SEMANTIC_MIN_SCORE
    hits = [Hit(candidates[i], float(scores[i]), semantic_score=float(scores[i]))
            for i in order if scores[i] >= floor]
    return hits[:limit], model_name


def fuse(keyword_hits: list[Hit], semantic_hits: list[Hit], limit: int) -> list[Hit]:
    """Reciprocal rank fusion: robust way to merge two rankings with incomparable scores."""
    merged: dict[int, Hit] = {}
    for hits in (keyword_hits, semantic_hits):
        for rank, hit in enumerate(hits, start=1):
            entry = merged.setdefault(hit.chunk.pk, Hit(hit.chunk, 0.0))
            entry.score += 1.0 / (RRF_K + rank)
            entry.keyword_score = hit.keyword_score if hit.keyword_score is not None else entry.keyword_score
            entry.semantic_score = hit.semantic_score if hit.semantic_score is not None else entry.semantic_score
    return sorted(merged.values(), key=lambda h: h.score, reverse=True)[:limit]


def collapse(hits: list[Hit]) -> list[Hit]:
    """Show one hit per invoice / per page (the best-ranked chunk wins)."""
    seen, out = set(), []
    for hit in hits:
        c = hit.chunk
        key = (c.document_id, c.kind, c.result_id if c.kind == "invoice" else c.page_number)
        if key not in seen:
            seen.add(key)
            out.append(hit)
    return out


def snippet(text: str, tokens: list[str], width: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= width:
        return text
    position = min((p for p in (text.lower().find(t) for t in tokens) if p >= 0), default=0)
    start = max(0, position - width // 3)
    end = min(len(text), start + width)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def search(base, query: str, mode: str, limit: int, filters: dict) -> dict:
    base = apply_filters(base, filters)
    tokens = tokenize(query)
    wide = limit * 3          # leave room for collapsing duplicates
    model_name, hits = "", []
    if mode == "keyword":
        hits = keyword_search(base, query, wide)
    elif mode == "semantic":
        hits, model_name = semantic_search(base, query, wide)
    else:
        keyword_hits = keyword_search(base, query, wide)
        semantic_hits, model_name = semantic_search(base, query, wide)
        hits = fuse(keyword_hits, semantic_hits, wide)
    hits = collapse(hits)[:limit]
    return {"terms": tokens, "semantic_model": model_name or None, "hits": hits}


def parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
