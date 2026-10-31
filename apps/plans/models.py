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
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    billing_interval = models.CharField(
        max_length=20,
        choices=BillingInterval.choices,
        default=BillingInterval.MONTHLY
    )
    minimum_quantity = models.PositiveIntegerField(default=1)
    available_from = models.DateField(null=True, blank=True)
    available_until = models.DateField(null=True, blank=True)
    
    # Lifecycle policies
    auto_close = models.BooleanField(
        default=False,
        help_text="Automatically closes when the plan ends."
    )
    allow_early_close = models.BooleanField(
        default=True,
        help_text="Allow customer or staff to close subscription early."
    )
    allow_pause = models.BooleanField(
        default=True,
        help_text="Allow customer or staff to pause the subscription."
    )
    allow_renewal = models.BooleanField(
        default=True,
        help_text="Allow renewal of the subscription upon expiration."
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (${self.price}/{self.get_billing_interval_display()})"
