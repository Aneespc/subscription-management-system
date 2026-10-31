from django.conf import settings
from django.db import models
from django.utils import timezone
from datetime import timedelta
import uuid


class QuotationTemplate(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    validity_days = models.PositiveIntegerField(default=30, help_text="Number of days quotation stays valid")
    plan = models.ForeignKey("plans.Plan", on_delete=models.CASCADE, related_name="quotation_templates")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_templates"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.plan.name} - {self.validity_days} days)"


class QuotationTemplateLine(models.Model):
    template = models.ForeignKey(QuotationTemplate, on_delete=models.CASCADE, related_name="template_lines")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)
    variant = models.ForeignKey("products.ProductVariant", on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.product.name} x {self.quantity} for {self.template.name}"


class Quotation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        QUOTATION = "QUOTATION", "Quotation Sent"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CANCELLED = "CANCELLED", "Cancelled"
        CONVERTED = "CONVERTED", "Converted to Subscription"

    class PaymentTerms(models.TextChoices):
        IMMEDIATE = "IMMEDIATE", "Immediate Payment"
        NET_15 = "NET_15", "Net 15 Days"
        NET_30 = "NET_30", "Net 30 Days"
        NET_60 = "NET_60", "Net 60 Days"

    quotation_number = models.CharField(max_length=64, unique=True, blank=True)
    customer = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="quotations"
    )
    template = models.ForeignKey(
        QuotationTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotations"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_quotations"
    )
    issue_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
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
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.quotation_number:
            count = Quotation.objects.count() + 1
            self.quotation_number = f"QT-{timezone.now().year}-{count:04d}"
        if not self.expiry_date:
            validity = self.template.validity_days if self.template else 30
            self.expiry_date = (self.issue_date or timezone.now().date()) + timedelta(days=validity)
        super().save(*args, **kwargs)

    def is_expired(self):
        if self.expiry_date and self.status in [self.Status.DRAFT, self.Status.QUOTATION]:
            return self.expiry_date < timezone.now().date()
        return False

    def __str__(self):
        return f"{self.quotation_number} - {self.customer.company_name} ({self.get_status_display()})"


class QuotationLine(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)
    variant = models.ForeignKey("products.ProductVariant", on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def save(self, *args, **kwargs):
        # Auto-compute unit price if 0
        if not self.unit_price or self.unit_price == 0:
            base_price = self.product.sales_price
            extra = self.variant.price_extra if self.variant else 0
            self.unit_price = base_price + extra
        self.amount = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        variant_str = f" ({self.variant.attribute_value})" if self.variant else ""
        return f"{self.product.name}{variant_str} x {self.quantity} - ${self.amount}"
