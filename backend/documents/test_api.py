"""Tests for the REST API, background tasks, corrections and security behaviour.

Celery runs eagerly (inline) in these tests and the LLM is switched off, so nothing
touches Redis or the network, whatever is in your .env file.
"""
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pymupdf
from celery.exceptions import SoftTimeLimitExceeded
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import ScopedRateThrottle

from config import celery_app
from .extraction.llm import get_llm_client
from .models import CorrectionLog, CrossVerification, Document, ExtractionResult, ProcessingEvent
from .tasks import process_document_task
from .test_extraction import invoice_pdf

User = get_user_model()


class ApiTestCase(APITestCase):
    def setUp(self):
        cache.clear()                                        # throttle counters live in the cache
        self.tmp = Path(tempfile.mkdtemp())
        media = tempfile.mkdtemp()
        for override in (override_settings(MEDIA_ROOT=media, GROQ_API_KEY="", GROQ_MODEL=""),):
            override.enable()
            self.addCleanup(override.disable)
        previous = (celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates)
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True
        self.addCleanup(lambda: (setattr(celery_app.conf, "task_always_eager", previous[0]),
                                 setattr(celery_app.conf, "task_eager_propagates", previous[1])))
        self.addCleanup(shutil.rmtree, media, True)
        self.addCleanup(shutil.rmtree, self.tmp, True)

        self.alice = User.objects.create_user("alice", password="Alice-pass-12345")
        self.bob = User.objects.create_user("bob", password="Bob-pass-12345")
        self.staff = User.objects.create_user("root", password="Root-pass-12345", is_staff=True)
        self.login(self.alice)
        self.assertIsNone(get_llm_client())                  # tests must never call a real LLM

    def login(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    # ---- helpers
    def pdf_bytes(self, **kw) -> bytes:
        path = self.tmp / "tmp.pdf"
        invoice_pdf(path, **kw)
        return path.read_bytes()

    def upload(self, *files, expect=202):
        """files: (name, bytes). Runs the queued background jobs before returning."""
        payload = [SimpleUploadedFile(name, data) for name, data in files]
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/documents/", {"files": payload}, format="multipart")
        self.assertEqual(response.status_code, expect, response.content)
        return response

    def upload_one(self, name="inv.pdf", data=None, **kw) -> Document:
        response = self.upload((name, data or self.pdf_bytes(**kw)))
        return Document.objects.get(pk=response.json()["documents"][0]["id"])

    def xlsx_bytes(self, total=192.5, number="INV-1001") -> bytes:
        wb = Workbook()
        wb.active.append(["Invoice No", "Date", "Supplier", "Customer", "Total", "Currency"])
        wb.active.append([number, "2025-03-01", "Acme Trading Ltd", "Globex Corporation", total, "USD"])
        path = self.tmp / "reg.xlsx"
        wb.save(path)
        return path.read_bytes()


# =========================================================================== authentication
class AuthTests(ApiTestCase):
    def test_health_is_public_but_everything_else_needs_a_token(self):
        anonymous = APIClient()
        self.assertEqual(anonymous.get("/api/health/").status_code, 200)
        for url in ("/api/documents/", "/api/stats/", "/api/results/1/", "/api/auth/me/"):
            self.assertEqual(anonymous.get(url).status_code, 401, url)
        self.assertEqual(anonymous.post("/api/documents/", {}).status_code, 401)

    def test_login_returns_a_working_token(self):
        response = APIClient().post("/api/auth/token/", {"username": "alice", "password": "Alice-pass-12345"})
        self.assertEqual(response.status_code, 200)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {response.json()['token']}")
        self.assertEqual(client.get("/api/auth/me/").json()["username"], "alice")

    def test_wrong_password_and_invalid_token_are_rejected(self):
        self.assertEqual(APIClient().post("/api/auth/token/", {"username": "alice", "password": "nope"}).status_code, 400)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
        self.assertEqual(client.get("/api/documents/").status_code, 401)

    def test_login_is_rate_limited(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"login": "3/min"}):
            codes = [APIClient().post("/api/auth/token/", {"username": "alice", "password": "bad"}).status_code
                     for _ in range(5)]
        self.assertEqual(codes[:3], [400, 400, 400])
        self.assertEqual(codes[3:], [429, 429])


# =========================================================================== upload
class UploadTests(ApiTestCase):
    def test_upload_is_accepted_queued_and_processed_in_the_background(self):
        response = self.upload(("inv.pdf", self.pdf_bytes()))
        body = response.json()
        self.assertEqual(len(body["documents"]), 1)
        self.assertEqual(body["rejected"], [])
        self.assertEqual(body["documents"][0]["status"], "queued")      # returned before the worker ran

        document = Document.objects.get()
        self.assertEqual(document.status, Document.Status.COMPLETED)     # ...and finished by the background job
        self.assertEqual(document.owner, self.alice)
        self.assertEqual(document.results.get().invoice_number, "INV-1001")

    def test_multiple_files_with_one_invalid_are_partially_accepted(self):
        response = self.upload(("a.pdf", self.pdf_bytes()), ("notes.docx", b"PK\x03\x04 hello"),
                               ("b.csv", b"Invoice No,Total\nINV-9,10\n"))
        body = response.json()
        self.assertEqual(len(body["documents"]), 2)
        self.assertEqual([r["filename"] for r in body["rejected"]], ["notes.docx"])
        self.assertIn("Unsupported", body["rejected"][0]["error"])
        self.assertEqual(Document.objects.count(), 2)

    def test_all_files_invalid_gives_400(self):
        response = self.upload(("empty.pdf", b""), expect=400)
        self.assertEqual(len(response.json()["rejected"]), 1)
        self.assertEqual(Document.objects.count(), 0)

    def test_no_files_gives_400(self):
        self.assertEqual(self.client.post("/api/documents/", {}, format="multipart").status_code, 400)

    @override_settings(MAX_FILES_PER_UPLOAD=2)
    def test_too_many_files_is_rejected(self):
        response = self.upload(("a.csv", b"a,b\n1,2"), ("b.csv", b"a,b\n1,2"), ("c.csv", b"a,b\n1,2"), expect=400)
        self.assertIn("at most 2", response.json()["detail"])

    def test_file_content_must_match_its_extension(self):
        response = self.upload(("photo.png", self.pdf_bytes()), expect=400)
        self.assertIn("looks like PDF", response.json()["rejected"][0]["error"])

    @override_settings(MAX_UPLOAD_SIZE_MB=1)
    def test_oversized_file_is_rejected(self):
        response = self.upload(("big.csv", b"a,b\n" + b"1,2\n" * 400_000), expect=400)
        self.assertIn("limit", response.json()["rejected"][0]["error"])

    def test_filename_is_sanitised_and_stored_under_a_random_name(self):
        document = self.upload_one(name="../../etc/passwd.pdf")
        self.assertEqual(document.original_filename, "passwd.pdf")
        self.assertNotIn("passwd", document.file.name)
        self.assertTrue(document.file.name.startswith("uploads/"))
        self.assertTrue(Path(document.file.path).exists())

    def test_corrupt_but_well_labelled_file_is_accepted_then_fails_in_the_background(self):
        document = self.upload_one("broken.pdf", b"%PDF-1.4 this is not a real pdf" + bytes(300))
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertTrue(document.error_message)

    def test_upload_is_rate_limited(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"uploads": "2/hour"}):
            self.upload(("a.csv", b"Invoice No,Total\nINV-1,1\n"))
            self.upload(("b.csv", b"Invoice No,Total\nINV-2,1\n"))
            self.upload(("c.csv", b"Invoice No,Total\nINV-3,1\n"), expect=429)

    def test_broker_outage_leaves_a_recoverable_failed_document(self):
        with mock.patch.object(process_document_task, "delay", side_effect=ConnectionError("redis down")):
            document = self.upload_one("inv.pdf")
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertIn("could not be queued", document.error_message)
        self.assertEqual(self.client.post(f"/api/documents/{document.pk}/reprocess/").status_code, 202)
        document.refresh_from_db()


# =========================================================================== reading
class ReadingTests(ApiTestCase):
    def test_list_is_scoped_filtered_searchable_and_paginated(self):
        mine = self.upload_one("alice-invoice.pdf")
        self.upload_one("alice-register.csv", b"Invoice No,Total\nINV-5,10\n")
        self.login(self.bob)
        self.upload(("bob-invoice.pdf", self.pdf_bytes(number="INV-777")))
        self.login(self.alice)

        listing = self.client.get("/api/documents/").json()
        self.assertEqual(listing["count"], 2)
        self.assertNotIn("bob-invoice.pdf", [d["original_filename"] for d in listing["results"]])
        self.assertEqual(self.client.get("/api/documents/?q=register").json()["count"], 1)
        self.assertEqual(self.client.get("/api/documents/?file_type=pdf").json()["count"], 1)
        self.assertEqual(self.client.get("/api/documents/?status=failed").json()["count"], 0)
        self.assertEqual(self.client.get("/api/documents/?page_size=1").json()["results"].__len__(), 1)
        first = self.client.get("/api/documents/?ordering=original_filename").json()["results"][0]
        self.assertEqual(first["original_filename"], "alice-invoice.pdf")
        self.assertEqual(first["invoice_count"], 1)
        self.assertEqual(mine.pk.hex, first["id"].replace("-", ""))

    def test_users_cannot_see_each_others_documents_but_staff_can(self):
        document = self.upload_one()
        self.login(self.bob)
        for suffix in ("", "status/", "results/", "pages/", "file/"):
            self.assertEqual(self.client.get(f"/api/documents/{document.pk}/{suffix}").status_code, 404, suffix)
        self.assertEqual(self.client.delete(f"/api/documents/{document.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/documents/{document.pk}/reprocess/").status_code, 404)
        result = document.results.get()
        self.assertEqual(self.client.get(f"/api/results/{result.pk}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/results/{result.pk}/", {"total": "1"}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/results/{result.pk}/approve/").status_code, 404)
        self.login(self.staff)
        self.assertEqual(self.client.get(f"/api/documents/{document.pk}/").status_code, 200)

    def test_status_shows_progress_and_history(self):
        document = self.upload_one()
        body = self.client.get(f"/api/documents/{document.pk}/status/").json()
        self.assertEqual((body["status"], body["progress"]), ("completed", 100))
        stages = [(e["stage"], e["outcome"]) for e in body["events"]]
        for expected in [("upload", "success"), ("text_extraction", "success"), ("ai_extraction", "success"),
                         ("validation", "success"), ("cross_verification", "success")]:
            self.assertIn(expected, stages)

    def test_results_include_line_items_issues_and_cross_checks(self):
        document = self.upload_one(total="200.00")
        body = self.client.get(f"/api/documents/{document.pk}/results/").json()
        result = body["results"][0]
        self.assertEqual((result["invoice_number"], result["supplier_name"], result["total"]),
                         ("INV-1001", "Acme Trading Ltd", "200.00"))
        self.assertEqual(len(result["line_items"]), 2)
        self.assertEqual(result["review_status"], "needs_review")
        self.assertIn("TOTAL_MISMATCH", [i["code"] for i in result["issues"]])
        self.assertEqual(body["document"]["status"], "needs_review")
        self.assertEqual(body["cross_checks"], [])

    def test_pages_endpoint_can_omit_text(self):
        document = self.upload_one()
        with_text = self.client.get(f"/api/documents/{document.pk}/pages/").json()["results"][0]
        without = self.client.get(f"/api/documents/{document.pk}/pages/?include_text=false").json()["results"][0]
        self.assertIn("INV-1001", with_text["text"])
        self.assertNotIn("text", without)

    def test_original_file_download_headers(self):
        pdf = self.upload_one("inv.pdf")
        csv = self.upload_one("reg.csv", b"Invoice No,Total\nINV-5,10\n")
        inline = self.client.get(f"/api/documents/{pdf.pk}/file/")
        self.assertEqual(inline["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(inline.streaming_content).startswith(b"%PDF"))
        self.assertNotIn("attachment", inline["Content-Disposition"])
        self.assertIn("sandbox", inline["Content-Security-Policy"])
        self.assertEqual(inline["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", self.client.get(f"/api/documents/{csv.pk}/file/")["Content-Disposition"])
        self.assertIn("attachment", self.client.get(f"/api/documents/{pdf.pk}/file/?download=1")["Content-Disposition"])

    def test_delete_removes_the_document_its_file_and_results(self):
        document = self.upload_one()
        path = Path(document.file.path)
        self.assertTrue(path.exists())
        self.assertEqual(self.client.delete(f"/api/documents/{document.pk}/").status_code, 204)
        self.assertFalse(path.exists())
        self.assertEqual((Document.objects.count(), ExtractionResult.objects.count()), (0, 0))

    def test_stats(self):
        self.upload_one("good.pdf")
        self.upload_one("bad.pdf", b"%PDF-1.4 broken" + bytes(300))
        stats = self.client.get("/api/stats/").json()
        self.assertEqual(stats["documents"]["total"], 2)
        self.assertEqual(stats["documents"]["by_status"], {"completed": 1, "failed": 1})
        self.assertEqual(stats["processing"]["success_rate"], 0.5)
        self.assertEqual(stats["invoices"]["total"], 1)
        self.login(self.bob)
        self.assertEqual(self.client.get("/api/stats/").json()["documents"]["total"], 0)


# =========================================================================== reprocessing
class ReprocessTests(ApiTestCase):
    def test_failed_document_can_be_reprocessed_after_the_cause_is_fixed(self):
        document = self.upload_one("inv.pdf", b"%PDF-1.4 broken" + bytes(300))
        self.assertEqual(document.status, Document.Status.FAILED)
        Path(document.file.path).write_bytes(self.pdf_bytes())          # e.g. the storage problem was repaired

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/api/documents/{document.pk}/reprocess/")
        self.assertEqual(response.status_code, 202)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.assertEqual(document.attempts, 2)
        self.assertEqual(document.results.count(), 1)
        self.assertEqual(document.error_message, "")
        self.assertTrue(document.events.filter(stage="reprocess").exists())

    def test_reprocessing_a_finished_document_needs_confirmation(self):
        document = self.upload_one()
        response = self.client.post(f"/api/documents/{document.pk}/reprocess/")
        self.assertEqual(response.status_code, 409)
        self.assertIn("force", response.json()["detail"])
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(f"/api/documents/{document.pk}/reprocess/", {"force": True},
                                              format="json").status_code, 202)
        document.refresh_from_db()
        self.assertEqual(document.attempts, 2)

    def test_active_documents_cannot_be_reprocessed(self):
        document = self.upload_one()
        for state in (Document.Status.QUEUED, Document.Status.PROCESSING):
            Document.objects.filter(pk=document.pk).update(status=state)
            self.assertEqual(self.client.post(f"/api/documents/{document.pk}/reprocess/", {"force": True},
                                              format="json").status_code, 409)

    def test_reprocess_all_failed(self):
        failed = self.upload_one("bad.pdf", b"%PDF-1.4 broken" + bytes(300))
        good = self.upload_one("good.pdf")
        with self.captureOnCommitCallbacks(execute=True):
            body = self.client.post("/api/documents/reprocess-failed/").json()
        self.assertEqual(body["queued"], 1)
        failed.refresh_from_db()
        good.refresh_from_db()
        self.assertEqual((failed.attempts, good.attempts), (2, 1))


# =========================================================================== corrections
class CorrectionTests(ApiTestCase):
    def test_correcting_a_wrong_total_clears_the_issue_and_keeps_an_audit_trail(self):
        document = self.upload_one(total="200.00")
        result = document.results.get()
        self.assertEqual(document.status, Document.Status.NEEDS_REVIEW)

        response = self.client.patch(f"/api/results/{result.pk}/", {"total": "192.50", "note": "typo on the invoice"},
                                     format="json")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["total"], "192.50")
        self.assertEqual(body["review_status"], "ok")
        self.assertNotIn("TOTAL_MISMATCH", [i["code"] for i in body["issues"]])
        self.assertEqual([(c["field"], c["old_value"], c["new_value"], c["note"]) for c in body["corrections"]],
                         [("total", "200.00", "192.50", "typo on the invoice")])
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.COMPLETED)

    def test_unchanged_values_are_not_logged(self):
        result = self.upload_one().results.get()
        self.client.patch(f"/api/results/{result.pk}/", {"total": "192.50", "supplier_name": "Acme  Trading Ltd"},
                          format="json")
        self.assertEqual(CorrectionLog.objects.count(), 0)

    def test_clearing_a_required_field_raises_a_missing_field_issue(self):
        result = self.upload_one().results.get()
        body = self.client.patch(f"/api/results/{result.pk}/", {"supplier_name": None}, format="json").json()
        self.assertIsNone(body["supplier_name"])
        self.assertEqual(body["review_status"], "needs_review")
        self.assertTrue(any(i["code"] == "MISSING_FIELD" and i["field"] == "supplier_name" for i in body["issues"]))

    def test_supplier_change_updates_duplicate_key(self):
        result = self.upload_one().results.get()
        self.client.patch(f"/api/results/{result.pk}/", {"supplier_name": "Beta Co"}, format="json")
        result.refresh_from_db()
        self.assertEqual(result.dedupe_key, "betaco|inv1001")

    def test_line_items_can_be_replaced_and_are_revalidated(self):
        result = self.upload_one().results.get()
        body = self.client.patch(f"/api/results/{result.pk}/", {"line_items": [
            {"description": "Widget A", "quantity": "2", "unit_price": "50", "amount": "110"},
            {"description": "Gadget B", "quantity": "1", "unit_price": "75", "amount": "75"}]}, format="json").json()
        self.assertEqual(len(body["line_items"]), 2)
        codes = [i["code"] for i in body["issues"]]
        self.assertIn("LINE_ITEM_MISMATCH", codes)
        self.assertIn("SUBTOTAL_MISMATCH", codes)
        self.assertEqual(body["corrections"][0]["field"], "line_items")

    def test_invalid_corrections_are_rejected(self):
        result = self.upload_one().results.get()
        url = f"/api/results/{result.pk}/"
        for payload in ({}, {"note": "only a note"}, {"currency": "DOLLARS"}, {"invoice_date": "not-a-date"},
                        {"total": "12.345"}, {"total": "abc"}, {"line_items": [{"amount": "x"}]},
                        {"invoice_number": "x" * 101}):
            self.assertEqual(self.client.patch(url, payload, format="json").status_code, 400, payload)
        self.assertEqual(CorrectionLog.objects.count(), 0)

    def test_approve_marks_issues_resolved_and_the_document_complete(self):
        document = self.upload_one(total="200.00")
        result = document.results.get()
        body = self.client.post(f"/api/results/{result.pk}/approve/").json()
        self.assertEqual(body["review_status"], "reviewed")
        self.assertTrue(all(i["resolved"] for i in body["issues"]))
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.COMPLETED)

    def test_resolving_a_single_issue(self):
        document = self.upload_one(total="200.00")
        issues = document.results.get().issues.filter(severity__in=("error", "warning"))
        self.assertEqual(issues.count(), 1)
        issue = issues.get()
        self.assertEqual(self.client.post(f"/api/issues/{issue.pk}/resolve/").status_code, 200)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.COMPLETED)
        self.login(self.bob)
        self.assertEqual(self.client.post(f"/api/issues/{issue.pk}/resolve/").status_code, 404)

    def test_manual_entry_for_a_document_where_nothing_was_found(self):
        path = self.tmp / "letter.pdf"
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 100), "Dear customer, thank you for visiting our office last week.")
        doc.save(path)
        doc.close()
        document = self.upload_one("letter.pdf", path.read_bytes())
        self.assertEqual(document.status, Document.Status.NEEDS_REVIEW)
        self.assertEqual(document.results.count(), 0)

        response = self.client.post(f"/api/documents/{document.pk}/results/", {
            "invoice_number": "M-1", "invoice_date": "2025-04-01", "supplier_name": "Acme Ltd",
            "customer_name": "Globex", "currency": "usd", "subtotal": "100.00", "tax": "10.00", "total": "110.00"},
            format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["method"], body["currency"], body["review_status"]), ("manual", "USD", "ok"))
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.COMPLETED)

    def test_corrections_are_blocked_while_a_document_is_processing(self):
        document = self.upload_one()
        result = document.results.get()
        Document.objects.filter(pk=document.pk).update(status=Document.Status.PROCESSING)
        self.assertEqual(self.client.patch(f"/api/results/{result.pk}/", {"total": "1"}, format="json").status_code, 409)
        self.assertEqual(self.client.post(f"/api/documents/{document.pk}/results/", {"total": "1"},
                                          format="json").status_code, 409)

    def test_fixing_one_side_of_a_pdf_excel_mismatch_clears_it_on_both_documents(self):
        pdf = self.upload_one("inv.pdf")
        sheet = self.upload_one("register.xlsx", self.xlsx_bytes(total=250))
        check = CrossVerification.objects.get()
        self.assertEqual(check.outcome, "mismatch")
        for document in (pdf, sheet):
            document.refresh_from_db()
            self.assertEqual(document.status, Document.Status.NEEDS_REVIEW)

        sheet_result = sheet.results.get()
        self.client.patch(f"/api/results/{sheet_result.pk}/", {"total": "192.50"}, format="json")

        self.assertEqual(CrossVerification.objects.get().outcome, "match")
        for document in (pdf, sheet):
            document.refresh_from_db()
            self.assertEqual(document.status, Document.Status.COMPLETED, document.issues.values_list("code", flat=True))
        self.assertFalse(pdf.results.get().issues.filter(code="CROSS_CHECK_MISMATCH").exists())


# =========================================================================== background tasks
class TaskTests(ApiTestCase):
    def queued_document(self) -> Document:
        document = self.upload_one()
        Document.objects.filter(pk=document.pk).update(status=Document.Status.QUEUED)
        document.refresh_from_db()
        return document

    def test_missing_document_is_ignored(self):
        self.assertEqual(process_document_task.run("00000000-0000-0000-0000-000000000000"), "missing")

    def test_duplicate_messages_do_not_process_twice(self):
        document = self.upload_one()                       # already completed
        self.assertTrue(process_document_task.run(str(document.pk)).startswith("skipped"))
        document.refresh_from_db()
        self.assertEqual(document.attempts, 1)

    def test_a_queued_document_is_processed_once(self):
        document = self.queued_document()
        self.assertEqual(process_document_task.run(str(document.pk)), "completed")
        document.refresh_from_db()
        self.assertEqual(document.attempts, 2)

    def test_redelivered_message_resumes_an_interrupted_document(self):
        document = self.upload_one()
        Document.objects.filter(pk=document.pk).update(status=Document.Status.PROCESSING)   # worker died mid-job
        self.assertTrue(process_document_task.run(str(document.pk)).startswith("skipped"))   # ordinary duplicate
        process_document_task.push_request(delivery_info={"redelivered": True})
        try:
            self.assertEqual(process_document_task.run(str(document.pk)), "completed")
        finally:
            process_document_task.pop_request()

    def test_time_limit_marks_the_document_failed(self):
        document = self.queued_document()
        with mock.patch("documents.tasks.process_document", side_effect=SoftTimeLimitExceeded()):
            self.assertEqual(process_document_task.run(str(document.pk)), "timeout")
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.FAILED)
        self.assertIn("too long", document.error_message)

    def test_recover_stuck_documents(self):
        stuck = self.upload_one("a.pdf")
        waiting = self.upload_one("b.pdf", self.pdf_bytes(number="INV-2002"))
        fresh = self.upload_one("c.pdf", self.pdf_bytes(number="INV-3003"))
        old = timezone.now() - timedelta(hours=5)
        Document.objects.filter(pk=stuck.pk).update(status=Document.Status.PROCESSING, updated_at=old)
        Document.objects.filter(pk=waiting.pk).update(status=Document.Status.QUEUED, updated_at=old)
        Document.objects.filter(pk=fresh.pk).update(status=Document.Status.PROCESSING)

        with self.captureOnCommitCallbacks(execute=True):
            call_command("recover_stuck_documents", "--minutes", "60", stdout=mock.Mock())
        for document in (stuck, waiting, fresh):
            document.refresh_from_db()
        self.assertEqual(stuck.status, Document.Status.FAILED)
        self.assertIn("interrupted", stuck.error_message)
        self.assertEqual(waiting.status, Document.Status.COMPLETED)          # re-queued and processed
        self.assertEqual(fresh.status, Document.Status.PROCESSING)           # recent work is left alone

    def test_create_api_user_command(self):
        call_command("create_api_user", "carol", "--password", "Carol-pass-12345", stdout=mock.Mock())
        user = User.objects.get(username="carol")
        self.assertTrue(user.check_password("Carol-pass-12345"))
        self.assertTrue(Token.objects.filter(user=user).exists())
        self.assertEqual(APIClient().post("/api/auth/token/", {"username": "carol", "password": "Carol-pass-12345"}
                                          ).status_code, 200)
