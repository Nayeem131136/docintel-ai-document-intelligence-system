from django.contrib import admin

from . import models


class PageInline(admin.TabularInline):
    model = models.DocumentPage
    extra = 0
    fields = ("page_number", "source", "ocr_confidence", "has_error")
    show_change_link = True


@admin.register(models.Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "file_type", "status", "progress", "page_count", "uploaded_at")
    list_filter = ("status", "file_type")
    search_fields = ("original_filename", "sha256")
    readonly_fields = ("id", "sha256", "uploaded_at", "updated_at")
    inlines = [PageInline]


class LineItemInline(admin.TabularInline):
    model = models.LineItem
    extra = 0


@admin.register(models.ExtractionResult)
class ExtractionResultAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "supplier_name", "invoice_date", "total", "currency", "review_status")
    list_filter = ("review_status", "method", "currency")
    search_fields = ("invoice_number", "supplier_name", "customer_name")
    inlines = [LineItemInline]


admin.site.register(models.DocumentPage)
admin.site.register(models.ValidationIssue)
admin.site.register(models.CorrectionLog)
admin.site.register(models.ProcessingEvent)
admin.site.register(models.CrossVerification)
