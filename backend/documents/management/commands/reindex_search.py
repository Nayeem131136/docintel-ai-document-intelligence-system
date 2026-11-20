"""Rebuild the search index (needed after changing the embedding model).

    python manage.py reindex_search
    python manage.py reindex_search --document <uuid>
"""
from django.core.management.base import BaseCommand

from documents.models import Document
from documents.search.embeddings import get_embedder
from documents.search.indexer import index_document


class Command(BaseCommand):
    help = "Re-create the keyword/semantic search index from the stored pages and invoices."

    def add_arguments(self, parser):
        parser.add_argument("--document", help="Only this document id.")

    def handle(self, *args, **options):
        embedder = get_embedder()
        self.stdout.write(f"Embedding backend: {embedder.name}")
        documents = Document.objects.exclude(status__in=["queued", "processing", "failed"])
        if options["document"]:
            documents = documents.filter(pk=options["document"])
        total = 0
        for document in documents.iterator():
            total += index_document(document)
        self.stdout.write(self.style.SUCCESS(f"Indexed {total} chunk(s) across {documents.count()} document(s)."))
