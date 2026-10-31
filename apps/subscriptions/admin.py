from django.contrib import admin
from .models import Subscription, SubscriptionLine


class SubscriptionLineInline(admin.TabularInline):
    model = SubscriptionLine
    extra = 1


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "subscription_number", "customer", "plan", "status",
        "start_date", "expiry_date", "next_billing_date"
    )
    list_filter = ("status", "plan", "payment_terms", "start_date")
    search_fields = ("subscription_number", "customer__company_name")
    inlines = [SubscriptionLineInline]
