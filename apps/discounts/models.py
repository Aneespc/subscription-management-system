from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Discount(models.Model):
    class DiscountType(models.TextChoices):
        FIXED = "FIXED", "Fixed Amount"
        PERCENTAGE = "PERCENTAGE", "Percentage"

    class AppliesTo(models.TextChoices):
        ALL = "ALL", "All Items"
        PRODUCTS = "PRODUCTS", "Specific Products"
        SUBSCRIPTIONS = "SUBSCRIPTIONS", "Subscriptions"

    name = models.CharField(max_length=255)
    discount_type = models.CharField(
        max_length=20,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE,
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Fixed amount or percentage value",
    )
    minimum_purchase = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum subtotal required to apply this discount",
    )
    minimum_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum total item quantity required to apply this discount",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of times this discount can be used (null = unlimited)",
    )
    usage_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of times this discount has been applied",
    )
    applies_to = models.CharField(
        max_length=20,
        choices=AppliesTo.choices,
        default=AppliesTo.ALL,
        help_text="Scope of application: ALL items, specific PRODUCTS, or SUBSCRIPTIONS",
    )
    products = models.ManyToManyField(
        "products.Product",
        blank=True,
        related_name="discounts",
        help_text="Products this discount applies to when scope is PRODUCTS",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this discount is currently active",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_discounts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(value__gt=Decimal("0.00")),
                name="discount_value_gt_zero",
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="discount_end_date_gte_start_date",
            ),
        ]

    def __str__(self):
        if self.discount_type == self.DiscountType.PERCENTAGE:
            return f"{self.name} ({self.value}%)"
        return f"{self.name} (${self.value})"

    def clean(self):
        super().clean()
        if self.value is not None and self.value <= Decimal("0.00"):
            raise ValidationError({"value": "Discount value must be greater than zero."})

        if self.discount_type == self.DiscountType.PERCENTAGE and self.value is not None:
            if self.value < Decimal("0.00") or self.value > Decimal("100.00"):
                raise ValidationError({"value": "Percentage discount value must be between 0 and 100."})

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after start date."})

        if self.minimum_purchase is not None and self.minimum_purchase < Decimal("0.00"):
            raise ValidationError({"minimum_purchase": "Minimum purchase amount cannot be negative."})

    @property
    def is_currently_valid(self):
        """Check if active, within validity window, and usage limit not exhausted."""
        today = timezone.now().date()
        if not self.is_active:
            return False
        if today < self.start_date or today > self.end_date:
            return False
        if self.usage_limit is not None and self.usage_count >= self.usage_limit:
            return False
        return True

    @property
    def remaining_usages(self):
        if self.usage_limit is None:
            return None
        return max(0, self.usage_limit - self.usage_count)

    @property
    def formatted_value(self):
        if self.discount_type == self.DiscountType.PERCENTAGE:
            return f"{self.value}%"
        return f"${self.value:,.2f}"


class DiscountUsage(models.Model):
    discount = models.ForeignKey(
        Discount,
        on_delete=models.CASCADE,
        related_name="usages",
    )
    customer = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="discount_usages",
    )
    subscription = models.ForeignKey(
        "subscriptions.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_usages",
    )
    invoice = models.ForeignKey(
        "invoicing.Invoice",
        on_delete=models.CASCADE,
        related_name="discount_usages",
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-used_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["discount", "invoice"],
                name="unique_discount_per_invoice",
            ),
        ]
        indexes = [
            models.Index(fields=["customer"]),
            models.Index(fields=["subscription"]),
            models.Index(fields=["invoice"]),
            models.Index(fields=["used_at"]),
        ]

    def __str__(self):
        return f"{self.discount.name} on Invoice {self.invoice_id} (${self.discount_amount})"
