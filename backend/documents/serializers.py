
from rest_framework import serializers

from .models import (
    CorrectionLog,
    CrossVerification,
    Document,
    DocumentPage,
    ExtractionResult,
    LineItem,
    ProcessingEvent,
    ValidationIssue,
)


class IssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValidationIssue
        fields = [
            "id", "code", "severity", "field", "message",
            "expected", "found", "resolved", "created_at",
        ]


class LineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = LineItem
        fields = ["position", "description", "quantity", "unit_price", "amount"]


class CorrectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CorrectionLog
        fields = ["id", "field", "old_value", "new_value", "note", "corrected_at"]


class ResultSerializer(serializers.ModelSerializer):
    document = serializers.UUIDField(source="document_id", read_only=True)
    filename = serializers.CharField(source="document.original_filename", read_only=True)
    line_items = LineItemSerializer(many=True, read_only=True)
    issues = IssueSerializer(many=True, read_only=True)
    corrections = serializers.SerializerMethodField()

    class Meta:
        model = ExtractionResult
        fields = [
            "id", "document", "filename", "page_start", "page_end",
            "invoice_number", "invoice_date", "supplier_name", "customer_name",
            "currency", "subtotal", "discount", "tax", "total",
            "line_items", "confidence", "method", "model_name",
            "review_status", "issues", "corrections", "created_at", "updated_at",
        ]

    def get_corrections(self, obj):
        return CorrectionSerializer(obj.corrections.all()[:50], many=True).data


class ResultSummarySerializer(serializers.ModelSerializer):
    """Compact form used in lists."""
    document = serializers.UUIDField(source="document_id", read_only=True)
    filename = serializers.CharField(source="document.original_filename", read_only=True)
    open_issues = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ExtractionResult
        fields = [
            "id", "document", "filename", "invoice_number", "invoice_date",
            "supplier_name", "customer_name", "currency",
            "subtotal", "discount", "tax", "total",
            "review_status", "method", "open_issues", "created_at",
        ]


class DocumentSerializer(serializers.ModelSerializer):
    invoice_count = serializers.IntegerField(read_only=True, default=0)
    review_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Document
        fields = [
            "id", "original_filename", "file_type", "size_bytes", "status",
            "progress", "page_count", "pages_processed", "error_message",
            "attempts", "uploaded_at", "processed_at", "processing_time_ms",
            "invoice_count", "review_count",
        ]


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingEvent
        fields = ["stage", "outcome", "message", "duration_ms", "created_at"]


class CrossCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrossVerification
        fields = [
            "id", "check_type", "document_a", "document_b",
            "outcome", "details", "created_at",
        ]


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentPage
        fields = [
            "page_number", "sheet_name", "source", "ocr_confidence",
            "has_error", "error_message", "text",
        ]


class PageSummarySerializer(PageSerializer):
    class Meta(PageSerializer.Meta):
        fields = [f for f in PageSerializer.Meta.fields if f != "text"]


# ---------------------------------------------------------------------------
# Writes
class LineItemWriteSerializer(serializers.Serializer):
    description = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=2000
    )
    quantity = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, allow_null=True
    )
    unit_price = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, allow_null=True
    )
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )


class ResultWriteSerializer(serializers.Serializer):
    """Fields a reviewer may change. Send null to clear a value."""

    invoice_number = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True
    )
    invoice_date = serializers.DateField(required=False, allow_null=True)
    supplier_name = serializers.CharField(
        max_length=255, required=False, allow_null=True, allow_blank=True
    )
    customer_name = serializers.CharField(
        max_length=255, required=False, allow_null=True, allow_blank=True
    )
    currency = serializers.RegexField(
        r"^[A-Za-z]{3}$",
        required=False,
        allow_null=True,
        error_messages={"invalid": "Use a 3-letter currency code such as USD."},
    )
    subtotal = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    discount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    tax = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    total = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    line_items = LineItemWriteSerializer(many=True, required=False, max_length=500)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)

    def validate(self, attrs):
        if not any(key != "note" for key in attrs):
            raise serializers.ValidationError("Send at least one field to change.")
        return attrs
