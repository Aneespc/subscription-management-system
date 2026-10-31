from django.contrib import admin
from apps.discounts.models import Discount, DiscountUsage


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "discount_type",
        "value",
        "applies_to",
        "start_date",
        "end_date",
        "usage_count",
        "usage_limit",
        "is_active",
        "created_at",
    ]
    list_filter = ["discount_type", "applies_to", "is_active", "start_date", "end_date"]
    search_fields = ["name"]
    filter_horizontal = ["products"]
    readonly_fields = ["usage_count", "created_at"]


@admin.register(DiscountUsage)
class DiscountUsageAdmin(admin.ModelAdmin):
    list_display = ["discount", "customer", "invoice", "subscription", "discount_amount", "used_at"]
    list_filter = ["used_at", "discount"]
    search_fields = [
        "discount__name",
        "customer__company_name",
        "customer__user__username",
        "invoice__invoice_number",
        "subscription__subscription_number",
    ]
    readonly_fields = ["discount", "customer", "invoice", "subscription", "discount_amount", "used_at"]

