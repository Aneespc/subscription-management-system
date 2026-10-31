from django.db import models
from django.utils import timezone
from datetime import timedelta


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

    subscription_number = models.CharField(max_length=64, unique=True, blank=True)
    customer = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="subscriptions"
    )
    plan = models.ForeignKey(
        "plans.Plan",
        on_delete=models.PROTECT,
        related_name="subscriptions"
    )
    quotation = models.OneToOneField(
        "quotations.Quotation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription"
    )
    start_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    next_billing_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(
        max_length=20,
        choices=PaymentTerms.choices,
        default=PaymentTerms.NET_30
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.subscription_number:
            count = Subscription.objects.count() + 1
            self.subscription_number = f"SUB-{timezone.now().year}-{count:04d}"
        if not self.next_billing_date and self.status == self.Status.ACTIVE:
            self.next_billing_date = self.calculate_next_billing_date(self.start_date)
        super().save(*args, **kwargs)

    def calculate_next_billing_date(self, from_date=None):
        if not from_date:
            from_date = timezone.now().date()
        interval = self.plan.billing_interval
        if interval == "DAILY":
            return from_date + timedelta(days=1)
        elif interval == "WEEKLY":
            return from_date + timedelta(weeks=1)
        elif interval == "MONTHLY":
            # Rough 30 days
            return from_date + timedelta(days=30)
        elif interval == "YEARLY":
            return from_date + timedelta(days=365)
        return from_date + timedelta(days=30)

    @property
    def total_amount(self):
        return sum(line.amount for line in self.lines.all())

    @property
    def total_quantity(self):
        return sum(line.quantity for line in self.lines.all())

    @property
    def meets_minimum_quantity(self):
        return self.total_quantity >= self.plan.minimum_quantity

    # Policy checks
    def can_pause(self):
        return self.status == self.Status.ACTIVE and self.plan.allow_pause

    def can_resume(self):
        return self.status == self.Status.PAUSED

    def can_renew(self):
        return self.status in [self.Status.ACTIVE, self.Status.CLOSED] and self.plan.allow_renewal

    def can_close(self):
        if self.status in [self.Status.ACTIVE, self.Status.PAUSED, self.Status.CONFIRMED]:
            # If before expiry, check allow_early_close
            if self.expiry_date and self.expiry_date > timezone.now().date():
                return self.plan.allow_early_close
            return True
        return False

    def __str__(self):
        return f"{self.subscription_number} - {self.customer.company_name} ({self.plan.name}) [{self.get_status_display()}]"


class SubscriptionLine(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)
    variant = models.ForeignKey("products.ProductVariant", on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def save(self, *args, **kwargs):
        if not self.unit_price or self.unit_price == 0:
            base_price = self.product.sales_price
            extra = self.variant.price_extra if self.variant else 0
            self.unit_price = base_price + extra
        self.amount = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        variant_str = f" ({self.variant.attribute_value})" if self.variant else ""
        return f"{self.product.name}{variant_str} x {self.quantity} (${self.amount})"
