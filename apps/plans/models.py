from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
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
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    billing_interval = models.CharField(
        max_length=20, choices=BillingInterval.choices, default=BillingInterval.MONTHLY
    )
    minimum_quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
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
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="plan_price_gte_zero"),
            models.CheckConstraint(condition=Q(minimum_quantity__gte=1), name="plan_minimum_quantity_gte_one"),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_billing_interval_display()})"

    def clean(self):
        super().clean()
        if self.name and Plan.objects.filter(name__iexact=self.name.strip()).exclude(pk=self.pk).exists():
            raise ValidationError({"name": "A plan with this name already exists."})
        if self.available_from and self.available_until and self.available_until < self.available_from:
            raise ValidationError({"available_until": "Availability end must be on or after the start date."})

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
