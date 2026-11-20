"""Build and refresh the search index (SearchChunk rows) for documents and invoices."""
import logging
import re

from django.conf import settings
from django.db import transaction

from ..models import Document, ExtractionResult, SearchChunk
from .embeddings import embed_texts, to_bytes

logger = logging.getLogger(__name__)

BATCH = 32


def split_text(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    """Split on whitespace boundaries into overlapping pieces of roughly ``size`` characters."""
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    pieces, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            cut = cut if cut != -1 else text.rfind(" ", start + size // 2, end)
            end = cut if cut != -1 else end
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return pieces


def invoice_text(result: ExtractionResult) -> str:
    parts = []
    if result.invoice_number:
        parts.append(f"Invoice {result.invoice_number}")
    if result.supplier_name:
        parts.append(f"from {result.supplier_name}")
    if result.customer_name:
        parts.append(f"billed to {result.customer_name}")
    if result.invoice_date:
        parts.append(f"dated {result.invoice_date.isoformat()}")
    if result.total is not None:
        parts.append(f"total {result.total} {result.currency or ''}".strip())
    text = " ".join(parts)
    items = [i.description.strip() for i in result.line_items.all() if i.description and i.description.strip()]
    if items:
        text += ". Items: " + "; ".join(items)
    return text.strip()


def _embed_into(chunks: list[SearchChunk]) -> None:
    """Fill in the embedding of each chunk. A failure leaves the chunk keyword-searchable only."""
    for start in range(0, len(chunks), BATCH):
        batch = chunks[start:start + BATCH]
        try:
            vectors, name = embed_texts([c.text for c in batch])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embedding failed (%s); %d chunk(s) will be keyword-only.", type(exc).__name__, len(batch))
            continue
        for chunk, vector in zip(batch, vectors):
            chunk.embedding, chunk.embedding_model = to_bytes(vector), name


def index_result(result: ExtractionResult) -> None:
    """(Re)index one invoice, e.g. after a manual correction."""
    text = invoice_text(result)
    with transaction.atomic():
        result.chunks.filter(kind=SearchChunk.Kind.INVOICE).delete()
        if not text:
            return
        chunk = SearchChunk(document_id=result.document_id, result=result, kind=SearchChunk.Kind.INVOICE,
                            page_number=result.page_start, text=text)
        _embed_into([chunk])
        chunk.save()


def index_document(document: Document) -> int:
    """Rebuild every chunk of a document. Returns the number of chunks. Never raises for embedding problems."""
    chunks: list[SearchChunk] = []
    for result in document.results.prefetch_related("line_items"):
        text = invoice_text(result)
        if text:
            chunks.append(SearchChunk(document=document, result=result, kind=SearchChunk.Kind.INVOICE,
                                      page_number=result.page_start, text=text))
    limit = settings.EMBED_MAX_PAGES
    for page in document.pages.order_by("page_number")[:limit]:
        for index, piece in enumerate(split_text(page.text)):
            chunks.append(SearchChunk(document=document, kind=SearchChunk.Kind.PAGE, page_number=page.page_number,
                                      chunk_index=index, text=piece))
    _embed_into(chunks)
    with transaction.atomic():
        document.chunks.all().delete()
        SearchChunk.objects.bulk_create(chunks, batch_size=200)
    return len(chunks)


def safe_index_document(document: Document) -> None:
    """Indexing is a bonus step: it must never make a processed document fail."""
    try:
        index_document(document)
    except Exception:  # noqa: BLE001
        logger.exception("Search indexing failed for document %s", document.pk)


def safe_index_result(result: ExtractionResult) -> None:
    try:
        index_result(result)
    except Exception:  # noqa: BLE001
        logger.exception("Search indexing failed for result %s", result.pk)
