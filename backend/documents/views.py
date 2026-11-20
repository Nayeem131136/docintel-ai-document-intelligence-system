import hashlib
import logging
import mimetypes
import os
import re

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Avg, Count, Q
from django.http import FileResponse
from rest_framework import mixins, status as http, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import corrections
from .models import Document, ExtractionResult, ProcessingEvent, ValidationIssue
from .processing import ProcessingError
from .processing.detect import detect_upload_type
from .serializers import (CrossCheckSerializer, DocumentSerializer, EventSerializer, IssueSerializer,
                          PageSerializer, PageSummarySerializer, ResultSerializer, ResultSummarySerializer,
                          ResultWriteSerializer)
from .tasks import enqueue_document

logger = logging.getLogger(__name__)

CONTENT_TYPES = {"pdf": "application/pdf", "csv": "text/csv", "xls": "application/vnd.ms-excel",
                 "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}
ACTIVE = (Document.Status.QUEUED, Document.Status.PROCESSING)


def visible_documents(user):
    """Object-level access control: users see only their own documents (staff see all)."""
    queryset = Document.objects.all()
    return queryset if user.is_staff else queryset.filter(owner=user)


def visible_results(user):
    queryset = ExtractionResult.objects.select_related("document")
    return queryset if user.is_staff else queryset.filter(document__owner=user)


def clean_filename(name: str) -> str:
    """Keep only the base name, drop control characters, cap the length."""
    name = os.path.basename((name or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name) or "upload"
    stem, ext = os.path.splitext(name)
    return stem[: 255 - len(ext)] + ext


# --------------------------------------------------------------------------- health & auth
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def health(request):
    """Liveness / readiness probe. Reports database connectivity."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        database = "ok"
    except Exception:  # noqa: BLE001 - report any DB failure as "unavailable"
        database = "unavailable"
    healthy = database == "ok"
    return Response({"status": "ok" if healthy else "degraded", "service": "docintel-api",
                     "database": database, "debug": settings.DEBUG}, status=200 if healthy else 503)


class LoginView(APIView):
    """POST username + password, receive an API token (rate limited)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = AuthTokenSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.get_username(), "is_staff": user.is_staff})


class MeView(APIView):
    def get(self, request):
        return Response({"username": request.user.get_username(), "is_staff": request.user.is_staff})


# --------------------------------------------------------------------------- documents
class DocumentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                      viewsets.GenericViewSet):
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_scopes = {"create": "uploads", "reprocess": "reprocess", "reprocess_failed": "reprocess",
                       "status": "poll"}

    def initial(self, request, *args, **kwargs):
        self.throttle_scope = self.throttle_scopes.get(self.action)
        super().initial(request, *args, **kwargs)

    def get_queryset(self):
        queryset = visible_documents(self.request.user).annotate(
            invoice_count=Count("results", distinct=True),
            review_count=Count("results", filter=Q(results__review_status="needs_review"), distinct=True),
        )
        params = self.request.query_params
        if value := params.get("status"):
            queryset = queryset.filter(status__in=[v for v in value.split(",") if v])
        if value := params.get("file_type"):
            queryset = queryset.filter(file_type=value)
        if value := params.get("q"):
            queryset = queryset.filter(original_filename__icontains=value)
        ordering = params.get("ordering", "-uploaded_at")
        allowed = {"uploaded_at", "original_filename", "status", "size_bytes", "processing_time_ms"}
        if ordering.lstrip("-") in allowed:
            queryset = queryset.order_by(ordering)
        return queryset

    # ---- upload
    def create(self, request, *args, **kwargs):
        files = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not files:
            return Response({"detail": "No files were uploaded. Send one or more files in the 'files' field."},
                            status=http.HTTP_400_BAD_REQUEST)
        limit = settings.MAX_FILES_PER_UPLOAD
        if len(files) > limit:
            return Response({"detail": f"Too many files: at most {limit} per upload."},
                            status=http.HTTP_400_BAD_REQUEST)

        accepted, rejected = [], []
        for upload in files:
            name = clean_filename(upload.name)
            try:
                upload.seek(0)
                head = upload.read(2048)
                file_type = detect_upload_type(name, upload.size, head)
            except ProcessingError as exc:
                rejected.append({"filename": name, "error": str(exc)})
                continue

            digest = hashlib.sha256()
            for chunk in upload.chunks():
                digest.update(chunk)
            with transaction.atomic():
                document = Document(owner=request.user, original_filename=name, file_type=file_type,
                                    size_bytes=upload.size, sha256=digest.hexdigest())
                document.file.save(name, upload, save=False)
                document.save()
                ProcessingEvent.objects.create(document=document, stage=ProcessingEvent.Stage.UPLOAD,
                                               outcome=ProcessingEvent.Outcome.SUCCESS,
                                               message=f"Received {upload.size} bytes as {file_type}.")
                enqueue_document(document)
            document.refresh_from_db()
            accepted.append(DocumentSerializer(document).data)

        body = {"documents": accepted, "rejected": rejected}
        return Response(body, status=http.HTTP_202_ACCEPTED if accepted else http.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        from .extraction.crosscheck import clear_cross_checks

        document = self.get_object()
        clear_cross_checks(document)
        document.file.delete(save=False)
        document.delete()
        return Response(status=http.HTTP_204_NO_CONTENT)

    # ---- progress & history
    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        document = self.get_object()
        data = DocumentSerializer(document).data
        data["events"] = EventSerializer(document.events.all(), many=True).data
        return Response(data)

    # ---- results
    @action(detail=True, methods=["get", "post"])
    def results(self, request, pk=None):
        document = self.get_object()
        if request.method == "GET":
            results = (document.results.select_related("document").prefetch_related("line_items", "issues",
                                                                                     "corrections"))
            return Response({
                "document": DocumentSerializer(document).data,
                "results": ResultSerializer(results, many=True).data,
                "document_issues": IssueSerializer(document.issues.filter(result__isnull=True), many=True).data,
                "cross_checks": CrossCheckSerializer(
                    document.cross_checks_a.all() | document.cross_checks_b.all(), many=True).data,
            })
        if document.status in ACTIVE:
            return Response({"detail": "The document is still being processed."}, status=http.HTTP_409_CONFLICT)
        serializer = ResultWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = corrections.create_manual_result(document, serializer.validated_data)
        return Response(ResultSerializer(result).data, status=http.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def pages(self, request, pk=None):
        document = self.get_object()
        include_text = request.query_params.get("include_text", "true").lower() != "false"
        serializer = PageSerializer if include_text else PageSummarySerializer
        page = self.paginate_queryset(document.pages.all())
        return self.get_paginated_response(serializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        """The original upload. PDFs and images display inline; everything else downloads."""
        document = self.get_object()
        if not document.file or not document.file.storage.exists(document.file.name):
            raise NotFound("The original file is no longer available.")
        content_type = CONTENT_TYPES.get(document.file_type) or mimetypes.guess_type(document.original_filename)[0] \
            or "application/octet-stream"
        inline = content_type in INLINE_TYPES and request.query_params.get("download") != "1"
        response = FileResponse(document.file.open("rb"), content_type=content_type, as_attachment=not inline,
                                filename=document.original_filename)
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"   # uploaded content can never run scripts
        response["Cache-Control"] = "private, no-store"
        return response

    # ---- reprocessing
    @action(detail=True, methods=["post"])
    def reprocess(self, request, pk=None):
        document = self.get_object()
        force = str(request.data.get("force", "")).lower() in ("1", "true", "yes")
        if document.status in ACTIVE:
            return Response({"detail": f"The document is already {document.status}."},
                            status=http.HTTP_409_CONFLICT)
        if document.status != Document.Status.FAILED and not force:
            return Response(
                {"detail": f"The document is {document.status}. Reprocessing replaces its extracted results and "
                           "any manual corrections. Send {\"force\": true} to confirm."},
                status=http.HTTP_409_CONFLICT)
        self._requeue(document)
        return Response(DocumentSerializer(document).data, status=http.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="reprocess-failed")
    def reprocess_failed(self, request):
        queued = []
        for document in visible_documents(request.user).filter(status=Document.Status.FAILED):
            self._requeue(document)
            queued.append(str(document.pk))
        return Response({"queued": len(queued), "documents": queued}, status=http.HTTP_202_ACCEPTED)

    @staticmethod
    def _requeue(document: Document) -> None:
        with transaction.atomic():
            document.status = Document.Status.QUEUED
            document.progress = 0
            document.error_message = ""
            document.save(update_fields=["status", "progress", "error_message", "updated_at"])
            ProcessingEvent.objects.create(document=document, stage=ProcessingEvent.Stage.REPROCESS,
                                           outcome=ProcessingEvent.Outcome.STARTED, message="Reprocessing requested")
            enqueue_document(document)


# --------------------------------------------------------------------------- results & issues
class ResultViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ResultSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        return visible_results(self.request.user).prefetch_related("line_items", "issues", "corrections")

    def partial_update(self, request, *args, **kwargs):
        result = self.get_object()
        if result.document.status in ACTIVE:
            return Response({"detail": "The document is still being processed."}, status=http.HTTP_409_CONFLICT)
        serializer = ResultWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        note = data.pop("note", "")
        corrections.apply_correction(result, data, note=note)
        return Response(ResultSerializer(self.get_queryset().get(pk=result.pk)).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        result = self.get_object()
        corrections.approve_result(result)
        return Response(ResultSerializer(self.get_queryset().get(pk=result.pk)).data)


class ResolveIssueView(APIView):
    """Mark one issue as resolved (a reviewer accepts it)."""

    def post(self, request, pk):
        issues = ValidationIssue.objects.select_related("document")
        if not request.user.is_staff:
            issues = issues.filter(document__owner=request.user)
        issue = issues.filter(pk=pk).first()
        if issue is None:
            raise NotFound()
        issue.resolved = True
        issue.save(update_fields=["resolved"])
        if issue.result_id:
            corrections.refresh_review_state(issue.result)
        corrections.update_document_status(issue.document)
        return Response(IssueSerializer(issue).data)


class StatsView(APIView):
    """Counts and timings for the dashboard (also useful as measured evidence for the evaluation report)."""

    def get(self, request):
        documents = visible_documents(request.user)
        by_status = {row["status"]: row["n"] for row in documents.values("status").annotate(n=Count("id"))}
        finished = [by_status.get(s, 0) for s in ("completed", "needs_review", "failed")]
        succeeded = by_status.get("completed", 0) + by_status.get("needs_review", 0)
        processed = documents.exclude(processing_time_ms__isnull=True)
        results = visible_results(request.user)
        open_issues = ValidationIssue.objects.filter(resolved=False, severity__in=("error", "warning"))
        if not request.user.is_staff:
            open_issues = open_issues.filter(document__owner=request.user)
        return Response({
            "documents": {"total": documents.count(), "by_status": by_status},
            "processing": {
                "success_rate": round(succeeded / sum(finished), 4) if sum(finished) else None,
                "failure_rate": round(by_status.get("failed", 0) / sum(finished), 4) if sum(finished) else None,
                "avg_time_ms": round(processed.aggregate(v=Avg("processing_time_ms"))["v"] or 0) or None,
            },
            "invoices": {"total": results.count(),
                         "needs_review": results.filter(review_status="needs_review").count()},
            "open_issues": open_issues.count(),
        })
