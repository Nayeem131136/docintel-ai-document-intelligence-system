"""Tests for keyword, semantic and hybrid search, filters, isolation and index upkeep."""
import numpy as np
from django.core.management import call_command
from django.test import override_settings
from unittest import mock

from .models import Document, SearchChunk
from .search import embeddings
from .search.indexer import index_document, split_text
from .test_api import ApiTestCase, invoice_pdf  # noqa: F401  (shared helpers)


class EmbedderTests(ApiTestCase):
    def test_hashing_embedder_is_deterministic_normalised_and_prefers_similar_text(self):
        embedder = embeddings.HashingEmbedder()
        a, b, c = embedder.embed(["office chairs and desks", "office chair purchase", "quarterly tax filing"])
        again = embedder.embed(["office chairs and desks"])[0]
        self.assertTrue(np.allclose(a, again))
        self.assertAlmostEqual(float(np.linalg.norm(a)), 1.0, places=5)
        self.assertGreater(float(a @ b), float(a @ c))

    def test_empty_text_does_not_crash(self):
        vector = embeddings.HashingEmbedder().embed([""])[0]
        self.assertEqual(float(np.linalg.norm(vector)), 0.0)

    @override_settings(EMBEDDING_BACKEND="auto")
    def test_auto_backend_falls_back_when_the_model_cannot_load(self):
        embeddings.reset_embedder()
        self.addCleanup(embeddings.reset_embedder)
        with mock.patch.object(embeddings, "FastEmbedder", side_effect=OSError("offline")):
            self.assertEqual(embeddings.get_embedder().name, "hashing-384")

    @override_settings(EMBEDDING_BACKEND="fastembed")
    def test_explicit_fastembed_backend_reports_the_error(self):
        embeddings.reset_embedder()
        self.addCleanup(embeddings.reset_embedder)
        with mock.patch.object(embeddings, "FastEmbedder", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                embeddings.get_embedder()

    def test_split_text(self):
        self.assertEqual(split_text("  "), [])
        self.assertEqual(split_text("short text"), ["short text"])
        long = " ".join(f"word{i}" for i in range(600))
        pieces = split_text(long, size=500, overlap=80)
        self.assertGreater(len(pieces), 3)
        self.assertTrue(all(len(p) <= 520 for p in pieces))
        self.assertIn("word599", pieces[-1])
        self.assertTrue(set(long.split()) <= set(" ".join(pieces).split()))     # nothing lost


@override_settings(EMBEDDING_BACKEND="hashing", SEMANTIC_MIN_SCORE=0.05)
class SearchTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        embeddings.reset_embedder()
        self.addCleanup(embeddings.reset_embedder)
        self.doc1 = self.upload_one("acme.pdf", **dict(number="INV-1001"))
        self.doc2 = self.upload_one("b.pdf", self.pdf_bytes(number="INV-2002", supplier="Zenith Logistics Inc"))
        self.doc3 = self.upload_one("c.csv", b"Invoice No,Supplier,Total,Currency\nINV-3003,Omega Printing,75.00,EUR\n")

    def search(self, q, **params):
        response = self.client.get("/api/search/", {"q": q, **params})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_documents_are_indexed_after_processing(self):
        kinds = set(self.doc1.chunks.values_list("kind", flat=True))
        self.assertEqual(kinds, {"invoice", "page"})
        self.assertTrue(all(c.embedding and c.embedding_model == "hashing-384" for c in self.doc1.chunks.all()))

    def test_keyword_search_finds_invoice_by_number_supplier_and_item(self):
        by_number = self.search("INV-2002", mode="keyword")
        self.assertEqual(by_number["results"][0]["invoice"]["invoice_number"], "INV-2002")
        self.assertEqual(by_number["results"][0]["kind"], "invoice")
        by_supplier = self.search("zenith logistics", mode="keyword")
        self.assertEqual({r["invoice"]["invoice_number"] for r in by_supplier["results"] if r["kind"] == "invoice"},
                         {"INV-2002"})
        self.assertTrue(self.search("widget", mode="keyword")["count"] >= 2)

    def test_keyword_search_is_case_insensitive_and_requires_all_words(self):
        self.assertTrue(self.search("ZENITH", mode="keyword")["count"] >= 1)
        self.assertEqual(self.search("zenith omega", mode="keyword")["count"], 0)

    def test_page_text_hits_carry_page_numbers_and_snippets(self):
        hit = next(r for r in self.search("Zenith", mode="keyword")["results"] if r["kind"] == "page")
        self.assertEqual(hit["page_number"], 1)
        self.assertIn("Zenith", hit["snippet"])
        self.assertEqual(hit["document"]["filename"], "b.pdf")

    def test_semantic_search_ranks_related_text_first(self):
        body = self.search("printing services Omega", mode="semantic")
        self.assertEqual(body["semantic_model"], "hashing-384")
        self.assertEqual(body["results"][0]["document"]["filename"], "c.csv")
        self.assertIsNotNone(body["results"][0]["semantic_score"])

    def test_hybrid_combines_both(self):
        body = self.search("Omega Printing", mode="hybrid")
        top = body["results"][0]
        self.assertEqual(top["document"]["filename"], "c.csv")
        self.assertIsNotNone(top["keyword_score"])
        self.assertIsNotNone(top["semantic_score"])

    def test_one_hit_per_invoice_and_page(self):
        keys = [(r["document"]["id"], r["kind"], r["page_number"]) for r in self.search("INV", mode="keyword")["results"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_filters(self):
        self.assertEqual({r["invoice"]["currency"] for r in self.search("INV", currency="EUR", mode="keyword")["results"]},
                         {"EUR"})
        self.assertEqual(self.search("INV", supplier="zenith", mode="keyword")["count"], 1)
        self.assertEqual(self.search("INV", min_total="100", mode="keyword")["count"], 2)
        self.assertEqual(self.search("INV", max_total="80", mode="keyword")["count"], 1)
        self.assertEqual(self.search("INV", date_from="2099-01-01", mode="keyword")["count"], 0)
        self.assertTrue(all(r["kind"] == "page" for r in self.search("INV", kind="page", mode="keyword")["results"]))
        self.assertEqual({r["document"]["file_type"] for r in self.search("INV", file_type="csv", mode="keyword")["results"]},
                         {"csv"})
        self.assertEqual({r["document"]["id"] for r in self.search("INV", document=str(self.doc2.pk),
                                                                    mode="keyword")["results"]}, {str(self.doc2.pk)})

    def test_invalid_parameters_give_400(self):
        for params in ({"q": "x"}, {"q": ""}, {"q": "ab" * 200}, {"q": "invoice", "mode": "magic"},
                       {"q": "invoice", "limit": "abc"}, {"q": "invoice", "min_total": "abc"},
                       {"q": "invoice", "date_from": "yesterday"}, {"q": "invoice", "review_status": "nope"},
                       {"q": "invoice", "document": "not-a-uuid"}, {"q": "invoice", "kind": "other"}):
            self.assertEqual(self.client.get("/api/search/", params).status_code, 400, params)

    def test_limit_is_respected(self):
        self.assertEqual(self.search("INV", mode="keyword", limit=1)["count"], 1)

    def test_search_never_crosses_users(self):
        self.login(self.bob)
        for mode in ("keyword", "semantic", "hybrid"):
            self.assertEqual(self.search("Zenith Logistics", mode=mode)["count"], 0, mode)
        self.login(self.staff)
        self.assertTrue(self.search("Zenith", mode="keyword")["count"] >= 1)

    def test_search_requires_authentication(self):
        from rest_framework.test import APIClient
        self.assertEqual(APIClient().get("/api/search/", {"q": "invoice"}).status_code, 401)

    def test_special_characters_are_harmless(self):
        for q in ("%%", "' OR 1=1 --", "a_b", "\\\\", "<script>"):
            self.assertEqual(self.client.get("/api/search/", {"q": q + "x", "mode": "keyword"}).status_code, 200, q)

    def test_correction_updates_the_index(self):
        result = self.doc1.results.get()
        self.assertEqual(self.search("Quantum Freight", mode="keyword")["count"], 0)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(f"/api/results/{result.pk}/", {"supplier_name": "Quantum Freight"}, format="json")
        hits = self.search("Quantum Freight", mode="keyword")["results"]
        self.assertEqual(hits[0]["invoice"]["supplier_name"], "Quantum Freight")
        self.assertEqual(self.search("Acme Trading", mode="keyword", kind="invoice")["count"], 0)

    def test_reprocessing_does_not_duplicate_chunks(self):
        before = self.doc2.chunks.count()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/api/documents/{self.doc2.pk}/reprocess/", {"force": True}, format="json")
        self.assertEqual(self.doc2.chunks.count(), before)

    def test_deleting_a_document_removes_it_from_search(self):
        self.client.delete(f"/api/documents/{self.doc2.pk}/")
        self.assertEqual(self.search("Zenith", mode="keyword")["count"], 0)
        self.assertFalse(SearchChunk.objects.filter(document_id=self.doc2.pk).exists())

    def test_chunks_from_a_different_embedding_model_are_ignored_by_semantic_search(self):
        SearchChunk.objects.update(embedding_model="some-old-model")
        self.assertEqual(self.search("Omega Printing", mode="semantic")["count"], 0)
        self.assertGreater(self.search("Omega Printing", mode="keyword")["count"], 0)   # keyword still works
        call_command("reindex_search", stdout=mock.Mock())
        self.assertEqual(self.search("Omega Printing", mode="semantic")["results"][0]["document"]["filename"], "c.csv")

    def test_embedding_failure_does_not_break_processing_and_keyword_search_still_works(self):
        with mock.patch("documents.search.indexer.embed_texts", side_effect=RuntimeError("boom")):
            document = self.upload_one("d.pdf", self.pdf_bytes(number="INV-4004", supplier="Nimbus Cloud Ltd"))
        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.assertFalse(document.chunks.exclude(embedding=None).exists())
        self.assertEqual(self.search("Nimbus", mode="keyword")["count"] >= 1, True)

    def test_large_documents_are_capped(self):
        document = self.doc1
        with override_settings(EMBED_MAX_PAGES=0):
            index_document(document)
        self.assertEqual(set(document.chunks.values_list("kind", flat=True)), {"invoice"})


class InvoiceListTests(ApiTestCase):
    def test_invoice_list_filters_and_isolation(self):
        self.upload_one("a.pdf", number="INV-1001", total="200.00")
        self.upload_one("b.pdf", self.pdf_bytes(number="INV-2002", supplier="Zenith Logistics Inc"))
        self.login(self.bob)
        self.upload(("bob.pdf", self.pdf_bytes(number="INV-9999")))
        self.login(self.alice)

        listing = self.client.get("/api/results/").json()
        self.assertEqual(listing["count"], 2)
        self.assertEqual({r["invoice_number"] for r in listing["results"]}, {"INV-1001", "INV-2002"})
        self.assertEqual(self.client.get("/api/results/?q=zenith").json()["count"], 1)
        self.assertEqual(self.client.get("/api/results/?invoice_number=1001").json()["count"], 1)
        self.assertEqual(self.client.get("/api/results/?has_issues=1").json()["count"], 1)   # the 200.00 total mismatch
        self.assertEqual(self.client.get("/api/results/?review_status=needs_review").json()["count"], 1)
        self.assertEqual(self.client.get("/api/results/?min_total=500").json()["count"], 0)
        ordered = self.client.get("/api/results/?ordering=invoice_number").json()["results"]
        self.assertEqual([r["invoice_number"] for r in ordered], ["INV-1001", "INV-2002"])
        self.assertEqual(self.client.get("/api/results/?date_from=bad").status_code, 400)
        self.assertEqual(self.client.get("/api/results/?ordering=password").status_code, 200)   # ignored, not an error
