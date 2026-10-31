from django.contrib import admin
from apps.invoicing.models import Invoice, InvoiceLine, InvoiceTaxLine, Tax


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    fields = ["product", "description", "quantity", "unit_price", "tax_rate", "discount_amount", "amount"]
    readonly_fields = ["amount"]


class InvoiceTaxLineInline(admin.TabularInline):
    model = InvoiceTaxLine
    extra = 0
    fields = ["tax_name", "tax_rate", "taxable_amount", "tax_amount"]
    readonly_fields = ["tax_name", "tax_rate", "taxable_amount", "tax_amount"]


@admin.register(Tax)
class TaxAdmin(admin.ModelAdmin):
    list_display = ["name", "rate", "description", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "invoice_number",
        "customer",
        "subscription",
        "issue_date",
        "due_date",
        "subtotal",
        "discount_amount",
        "tax_amount",
        "total_amount",
        "status",
        "created_at",
    ]
    list_filter = ["status", "issue_date", "due_date"]
    search_fields = [
        "invoice_number",
        "customer__company_name",
        "customer__user__username",
        "customer__billing_email",
        "subscription__subscription_number",
    ]
    inlines = [InvoiceLineInline, InvoiceTaxLineInline]
    readonly_fields = ["invoice_number", "created_at", "updated_at"]
    date_hierarchy = "issue_date"

