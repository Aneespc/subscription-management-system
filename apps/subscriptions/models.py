from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone


class Subscription(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        QUOTATION = "QUOTATION", "Quotation"
        CONFIRMED = "CONFIRMED", "Confirmed"
        ACTIVE = "ACTIVE", "Active"
        PAUSED = "PAUSED", "Paused"
        CLOSED = "CLOSED", "Closed"

    class PaymentTerms(models.TextChoices):
        IMMEDIATE = "IMMEDIATE", "Immediate Payment"
        NET_15 = "NET_15", "Net 15 Days"
        NET_30 = "NET_30", "Net 30 Days"
        NET_60 = "NET_60", "Net 60 Days"

    TERM_DAYS = {"IMMEDIATE": 0, "NET_15": 15, "NET_30": 30, "NET_60": 60}

    subscription_number = models.CharField(max_length=64, unique=True, blank=True)
    customer = models.ForeignKey(
        "accounts.CustomerProfile", on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey("plans.Plan", on_delete=models.PROTECT, related_name="subscriptions")
    quotation = models.OneToOneField(
        "quotations.Quotation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription",
    )
    start_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField(null=True, blank=True)
    next_billing_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(
        max_length=20, choices=PaymentTerms.choices, default=PaymentTerms.NET_30
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["next_billing_date"]),
            models.Index(fields=["status", "next_billing_date"]),
            models.Index(fields=["expiry_date"]),
        ]

    def __str__(self):
        return f"{self.subscription_number} - {self.customer.company_name}"

    def save(self, *args, **kwargs):
        if not self.next_billing_date and self.status == self.Status.ACTIVE and self.plan_id:
            self.next_billing_date = self.calculate_next_billing_date(self.start_date)
        if self.subscription_number:
            super().save(*args, **kwargs)
            return
        with transaction.atomic():
            self.subscription_number = f"TMP-{timezone.now().timestamp()}"
            kwargs.pop("update_fields", None)
            super().save(*args, **kwargs)
            self.subscription_number = f"SUB-{self.start_date.year}-{self.pk:05d}"
            super().save(update_fields=["subscription_number"])

    def calculate_next_billing_date(self, from_date=None):
        from_date = from_date or timezone.localdate()
        return from_date + self.plan.interval_delta()

    @property
    def payment_terms_days(self):
        return self.TERM_DAYS.get(self.payment_terms, 30)

    @property
    def total_amount(self):
        annotated = getattr(self, "lines_total", None)
        if annotated is not None:
            return annotated
        return sum((line.amount for line in self.lines.all()), Decimal("0.00"))

    @property
    def total_quantity(self):
        annotated = getattr(self, "lines_quantity", None)
        if annotated is not None:
            return annotated
        return sum(line.quantity for line in self.lines.all())

    @property
    def meets_minimum_quantity(self):
        return self.total_quantity >= self.plan.minimum_quantity

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())

    def can_activate(self):
        return self.status in (self.Status.DRAFT, self.Status.QUOTATION, self.Status.CONFIRMED)

    def can_pause(self):
        return self.status == self.Status.ACTIVE and self.plan.allow_pause

    def can_resume(self):
        return self.status == self.Status.PAUSED

    def can_renew(self):
        return self.status in (self.Status.ACTIVE, self.Status.CLOSED) and self.plan.allow_renewal

    def can_close(self):
        if self.status not in (self.Status.ACTIVE, self.Status.PAUSED, self.Status.CONFIRMED):
            return False
        if self.expiry_date and self.expiry_date > timezone.localdate():
            return self.plan.allow_early_close
        return True


class SubscriptionLine(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT)
    variant = models.ForeignKey(
        "products.ProductVariant", on_delete=models.SET_NULL, null=True, blank=True
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def save(self, *args, **kwargs):
        if not self.unit_price:
            extra = self.variant.price_extra if self.variant else Decimal("0.00")
            self.unit_price = self.product.sales_price + extra
        if not self.tax_rate:
            self.tax_rate = self.product.tax_rate
        self.amount = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    @property
    def tax_amount(self):
        return (self.amount * self.tax_rate / Decimal("100")).quantize(Decimal("0.01"))
