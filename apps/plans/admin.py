from django.contrib import admin
from .models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "name", "price", "billing_interval", "minimum_quantity",
        "auto_close", "allow_early_close", "allow_pause", "allow_renewal", "is_active"
    )
    list_filter = ("billing_interval", "auto_close", "allow_pause", "allow_renewal", "is_active")
    search_fields = ("name",)
