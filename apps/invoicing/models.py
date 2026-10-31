from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


def quantize_currency(amount):
    """Utility function to round decimal amounts to 2 places with ROUND_HALF_UP."""
    if amount is None:
        return Decimal("0.00")
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class InvoiceSequence(models.Model):
    """
    Thread-safe and process-safe sequence generator for invoice numbers.
    E.g. INV-2026-000001
    """
    year = models.PositiveIntegerField(unique=True)
    last_sequence = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Invoice Sequence"
        verbose_name_plural = "Invoice Sequences"

    @classmethod
    def get_next_number(cls, year=None):
        if year is None:
            year = timezone.now().year
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(
                year=year,
                defaults={"last_sequence": 0},
            )
            seq.last_sequence += 1
            seq.save(update_fields=["last_sequence"])
            return f"INV-{year}-{seq.last_sequence:06d}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    invoice_number = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Unique invoice reference number, e.g. INV-2026-000123",
    )
    customer = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.PROTECT,
        related_name="invoices",
        db_index=True,
    )
    subscription = models.ForeignKey(
        "subscriptions.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        db_index=True,
    )
    issue_date = models.DateField(default=timezone.now, db_index=True)
    due_date = models.DateField(db_index=True)
    billing_period_start = models.DateField()
    billing_period_end = models.DateField()

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "billing_period_start", "billing_period_end"],
                name="unique_subscription_billing_period",
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["customer"]),
            models.Index(fields=["subscription"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.invoice_number} ({self.customer}) - {self.get_status_display()}"

    def clean(self):
        super().clean()
        if self.billing_period_start and self.billing_period_end:
            if self.billing_period_end < self.billing_period_start:
                raise ValidationError({
                    "billing_period_end": "Billing period end date must be on or after start date."
                })
        if self.issue_date and self.due_date:
            if self.due_date < self.issue_date:
                raise ValidationError({
                    "due_date": "Due date cannot be before issue date."
                })

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            year = self.issue_date.year if self.issue_date else timezone.now().year
            self.invoice_number = InvoiceSequence.get_next_number(year)
        self.subtotal = quantize_currency(self.subtotal)
        self.discount_amount = quantize_currency(self.discount_amount)
        self.tax_amount = quantize_currency(self.tax_amount)
        self.total_amount = quantize_currency(self.total_amount)
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        if self.status in (self.Status.DRAFT, self.Status.CONFIRMED):
            return self.due_date < timezone.now().date()
        return False

    @property
    def can_confirm(self):
        return self.status == self.Status.DRAFT

    @property
    def can_cancel(self):
        return self.status in (self.Status.DRAFT, self.Status.CONFIRMED)

    @property
    def can_mark_paid(self):
        return self.status in (self.Status.DRAFT, self.Status.CONFIRMED)

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    @property
    def is_cancelled(self):
        return self.status == self.Status.CANCELLED


class InvoiceLine(models.Model):
    """
    Snapshots product description, unit_price, tax_rate, and discount at invoice generation time.
    """
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.ForeignKey(
        "products.Tax",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Line net total = (quantity * unit_price) - discount_amount",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.description} ({self.quantity} x {self.unit_price})"

    def save(self, *args, **kwargs):
        self.unit_price = quantize_currency(self.unit_price)
        self.tax_rate = Decimal(str(self.tax_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.discount_amount = quantize_currency(self.discount_amount)
        if not self.amount:
            raw_subtotal = Decimal(self.quantity) * self.unit_price
            self.amount = quantize_currency(max(Decimal("0.00"), raw_subtotal - self.discount_amount))
        else:
            self.amount = quantize_currency(self.amount)
        super().save(*args, **kwargs)


class InvoiceTaxLine(models.Model):
    """
    Summarized tax breakdown for an invoice, grouped by tax rate/name.
    """
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="tax_lines",
    )
    tax_name = models.CharField(max_length=100)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["tax_rate", "tax_name"]

    def __str__(self):
        return f"{self.tax_name} ({self.tax_rate}%): ₹{self.tax_amount} on ₹{self.taxable_amount}"

    def save(self, *args, **kwargs):
        self.tax_rate = Decimal(str(self.tax_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.taxable_amount = quantize_currency(self.taxable_amount)
        self.tax_amount = quantize_currency(self.tax_amount)
        super().save(*args, **kwargs)

