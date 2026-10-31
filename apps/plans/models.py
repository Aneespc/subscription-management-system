# TEMP STUB: Owned by Member 2 (plans) - Minimal stub for Member 3 feature branch
from decimal import Decimal
from django.db import models


class Plan(models.Model):
    class BillingInterval(models.TextChoices):
        DAILY = "DAILY", "Daily"
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"
        YEARLY = "YEARLY", "Yearly"

    name = models.CharField(max_length=255)
    billing_interval = models.CharField(
        max_length=20,
        choices=BillingInterval.choices,
        default=BillingInterval.MONTHLY,
    )
    billing_interval_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of intervals between billings, e.g. 1 month, 3 months",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_billing_interval_display()})"

