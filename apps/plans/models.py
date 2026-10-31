from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import models
from django.utils import timezone


class Plan(models.Model):
    class BillingInterval(models.TextChoices):
        DAILY = "DAILY", "Daily"
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"
        YEARLY = "YEARLY", "Yearly"

    MONTHLY_FACTOR = {
        "DAILY": Decimal("30.4167"),
        "WEEKLY": Decimal("4.3452"),
        "MONTHLY": Decimal("1"),
        "YEARLY": Decimal("0.0833"),
    }

    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    billing_interval = models.CharField(
        max_length=20, choices=BillingInterval.choices, default=BillingInterval.MONTHLY
    )
    minimum_quantity = models.PositiveIntegerField(default=1)
    available_from = models.DateField(null=True, blank=True)
    available_until = models.DateField(null=True, blank=True)
    auto_close = models.BooleanField(default=False)
    allow_early_close = models.BooleanField(default=True)
    allow_pause = models.BooleanField(default=True)
    allow_renewal = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["price", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_billing_interval_display()})"

    def interval_delta(self):
        return {
            self.BillingInterval.DAILY: relativedelta(days=1),
            self.BillingInterval.WEEKLY: relativedelta(weeks=1),
            self.BillingInterval.YEARLY: relativedelta(years=1),
        }.get(self.billing_interval, relativedelta(months=1))

    @property
    def is_available(self):
        today = timezone.localdate()
        if not self.is_active:
            return False
        if self.available_from and today < self.available_from:
            return False
        if self.available_until and today > self.available_until:
            return False
        return True
