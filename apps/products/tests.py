from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.plans.models import Plan

from .models import Product, Tax


class ValidationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="a@x.com", email="a@x.com", password="Str0ng!Pass", role="ADMIN")
        self.client.force_login(self.admin)

    def product_payload(self, **overrides):
        data = {
            "name": "Widget", "product_type": "SOFTWARE", "sales_price": "10.00", "cost_price": "4.00", "tax": "", "notes": "", "is_active": "on",
            "variants-TOTAL_FORMS": "1", "variants-INITIAL_FORMS": "0", "variants-MIN_NUM_FORMS": "0", "variants-MAX_NUM_FORMS": "1000",
            "variants-0-attribute_name": "", "variants-0-attribute_value": "", "variants-0-price_extra": "0.00",
        }
        data.update(overrides)
        return data

    def test_negative_prices_rejected(self):
        response = self.client.post(reverse("products:create"), self.product_payload(sales_price="-1"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.exists())

    def test_negative_variant_extra_rejected(self):
        data = self.product_payload(**{"variants-0-attribute_name": "Brand", "variants-0-attribute_value": "Odoo", "variants-0-price_extra": "-5"})
        response = self.client.post(reverse("products:create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.exists())

    def test_duplicate_product_name_rejected(self):
        Product.objects.create(name="Widget")
        response = self.client.post(reverse("products:create"), self.product_payload(name="widget"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 1)

    def test_tax_rate_bounds(self):
        with self.assertRaises(ValidationError):
            Tax(name="Too high", rate=Decimal("120")).full_clean()
        response = self.client.post(reverse("invoicing:tax_create"), {"name": "VAT", "rate": "-2", "description": "", "is_active": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Tax.objects.exists())

    def test_plan_minimum_quantity_and_dates(self):
        payload = {"name": "P", "price": "10", "billing_interval": "MONTHLY", "minimum_quantity": "0", "available_from": "2026-02-01", "available_until": "2026-01-01", "is_active": "on"}
        response = self.client.post(reverse("plans:create"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Plan.objects.exists())
        self.assertIn("minimum_quantity", response.context["form"].errors)
        self.assertIn("available_until", response.context["form"].errors)
