from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


class QuotationTemplate(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    validity_days = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1), MaxValueValidator(365)])
    plan = models.ForeignKey("plans.Plan", on_delete=models.CASCADE, related_name="quotation_templates")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_templates"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.name and QuotationTemplate.objects.filter(name__iexact=self.name.strip()).exclude(pk=self.pk).exists():
            raise ValidationError({"name": "A template with this name already exists."})


class QuotationTemplateLine(models.Model):
    template = models.ForeignKey(QuotationTemplate, on_delete=models.CASCADE, related_name="template_lines")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)
    variant = models.ForeignKey("products.ProductVariant", on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=1), name="template_line_quantity_gte_one")]

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def tax_rate(self):
        return self.product.tax_rate

    @property
    def unit_price(self):
        extra = self.variant.price_extra if self.variant else Decimal("0.00")
        return self.product.sales_price + extra


class Quotation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        QUOTATION = "QUOTATION", "Sent"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CONVERTED = "CONVERTED", "Converted"

    class PaymentTerms(models.TextChoices):
        IMMEDIATE = "IMMEDIATE", "Immediate Payment"
        NET_15 = "NET_15", "Net 15 Days"
        NET_30 = "NET_30", "Net 30 Days"
        NET_60 = "NET_60", "Net 60 Days"

    quotation_number = models.CharField(max_length=64, unique=True, blank=True)
    customer = models.ForeignKey("accounts.CustomerProfile", on_delete=models.CASCADE, related_name="quotations")
    template = models.ForeignKey(
        QuotationTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="quotations"
    )
    plan = models.ForeignKey(
        "plans.Plan", on_delete=models.SET_NULL, null=True, blank=True, related_name="quotations"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_quotations"
    )
    issue_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(max_length=20, choices=PaymentTerms.choices, default=PaymentTerms.NET_30)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["expiry_date"])]

    def __str__(self):
        return f"{self.quotation_number} - {self.customer.company_name}"

    def clean(self):
        super().clean()
        if self.issue_date and self.expiry_date and self.expiry_date < self.issue_date:
            raise ValidationError({"expiry_date": "Expiry date must be on or after the issue date."})

    def save(self, *args, **kwargs):
        if not self.expiry_date:
            validity = self.template.validity_days if self.template else 30
            self.expiry_date = (self.issue_date or timezone.localdate()) + timedelta(days=validity)
        if not self.plan_id and self.template_id:
            self.plan = self.template.plan
        if self.quotation_number:
            super().save(*args, **kwargs)
            return
        with transaction.atomic():
            self.quotation_number = f"TMP-{timezone.now().timestamp()}"
            kwargs.pop("update_fields", None)
            super().save(*args, **kwargs)
            self.quotation_number = f"QT-{self.issue_date.year}-{self.pk:05d}"
            super().save(update_fields=["quotation_number"])

    @property
    def is_expired(self):
        if self.expiry_date and self.status in (self.Status.DRAFT, self.Status.QUOTATION):
            return self.expiry_date < timezone.localdate()
        return False

    @property
    def days_remaining(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.localdate()).days

    def can_send(self):
        return self.status == self.Status.DRAFT

    def can_confirm(self):
        return self.status in (self.Status.DRAFT, self.Status.QUOTATION) and not self.is_expired

    def can_convert(self):
        return self.status == self.Status.CONFIRMED


    def can_edit(self):
        return self.status in (self.Status.DRAFT, self.Status.QUOTATION)


class QuotationLine(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT)
    variant = models.ForeignKey("products.ProductVariant", on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))])
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="quotation_line_quantity_gte_one"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="quotation_line_unit_price_gte_zero"),
        ]

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
