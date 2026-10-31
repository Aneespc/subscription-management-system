from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Tax(models.Model):
    name = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Taxes"
        constraints = [models.CheckConstraint(condition=Q(rate__gte=Decimal("0.00")), name="tax_rate_gte_zero")]

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

    def clean(self):
        super().clean()
        if self.rate is not None and self.rate < Decimal("0.00"):
            raise ValidationError({"rate": "Tax rate cannot be negative."})


class Product(models.Model):
    class ProductType(models.TextChoices):
        SOFTWARE = "SOFTWARE", "Business Software"
        ADDON = "ADDON", "Add-on"
        SERVICE = "SERVICE", "Professional Service"
        CONSUMABLE = "CONSUMABLE", "Consumable"

    name = models.CharField(max_length=255)
    product_type = models.CharField(max_length=20, choices=ProductType.choices, default=ProductType.SOFTWARE)
    sales_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)
    tax = models.ForeignKey(Tax, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def tax_rate(self):
        return self.tax.rate if self.tax_id and self.tax.is_active else Decimal("0.00")


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    attribute_name = models.CharField(max_length=100)
    attribute_value = models.CharField(max_length=100)
    price_extra = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["product", "attribute_name", "attribute_value"]
        constraints = [
            models.UniqueConstraint(fields=["product", "attribute_name", "attribute_value"], name="unique_variant_per_product")
        ]

    def __str__(self):
        return f"{self.attribute_name}: {self.attribute_value}"

    @property
    def total_price(self):
        return self.product.sales_price + self.price_extra
