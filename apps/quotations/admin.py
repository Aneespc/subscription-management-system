from django.contrib import admin
from .models import Quotation, QuotationLine, QuotationTemplate, QuotationTemplateLine


class QuotationTemplateLineInline(admin.TabularInline):
    model = QuotationTemplateLine
    extra = 1


@admin.register(QuotationTemplate)
class QuotationTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "validity_days", "is_active", "created_by")
    inlines = [QuotationTemplateLineInline]


class QuotationLineInline(admin.TabularInline):
    model = QuotationLine
    extra = 1


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = (
        "quotation_number", "customer", "template", "status",
        "issue_date", "expiry_date", "total_amount"
    )
    list_filter = ("status", "payment_terms", "issue_date")
    search_fields = ("quotation_number", "customer__company_name")
    inlines = [QuotationLineInline]
