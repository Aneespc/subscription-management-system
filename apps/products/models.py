# TEMP STUB: Owned by Member 2 (products) - Minimal stub for Member 3 feature branch
from decimal import Decimal
from django.db import models


class Product(models.Model):
    PRODUCT_TYPES = [
        ("SOFTWARE", "Business Software"),
        ("ADDON", "Add-on"),
        ("SERVICE", "Professional Service"),
        ("CONSUMABLE", "Consumable"),
    ]

    name = models.CharField(max_length=255)
    product_type = models.CharField(max_length=50, choices=PRODUCT_TYPES, default="SOFTWARE")
    sales_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (${self.sales_price})"


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    attribute_name = models.CharField(max_length=100)  # e.g., "Brand", "Edition"
    attribute_value = models.CharField(max_length=100)  # e.g., "Odoo Brand", "Pro"
    price_extra = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def total_price(self):
        return self.product.sales_price + self.price_extra

    def __str__(self):
        return f"{self.product.name} - {self.attribute_name}: {self.attribute_value} (+${self.price_extra})"
        return self.name

