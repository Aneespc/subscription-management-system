import hashlib
import hmac
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomerProfile, User
from apps.invoicing.models import Invoice

from .models import GatewayOrder, Payment

KEYS = {"RAZORPAY_KEY_ID": "rzp_test_key", "RAZORPAY_KEY_SECRET": "secret", "RAZORPAY_WEBHOOK_SECRET": "whsecret", "RAZORPAY_ENABLED": True}


def sign(secret, message):
    return hmac.new(secret.encode(), message.encode() if isinstance(message, str) else message, hashlib.sha256).hexdigest()


@override_settings(**KEYS)
class RazorpayFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="c@x.com", email="c@x.com", password="Str0ng!Pass", role="CUSTOMER")
        self.customer = CustomerProfile.objects.create(user=self.user, company_name="C")
        other = User.objects.create_user(username="o@x.com", email="o@x.com", password="Str0ng!Pass", role="CUSTOMER")
        CustomerProfile.objects.create(user=other, company_name="O")
        self.other = other
        due = date.today() + timedelta(days=10)
        self.invoice = Invoice.objects.create(
            invoice_number="INV-RZP-1", customer=self.customer, total_amount=Decimal("500.00"), status="CONFIRMED",
            due_date=due, billing_period_start=due - timedelta(days=30), billing_period_end=due,
        )
        self.client.force_login(self.user)

    def start_checkout(self):
        with mock.patch("apps.payments.gateway.client") as client:
            client.return_value.order.create.return_value = {"id": "order_123", "currency": "INR"}
            response = self.client.post(reverse("payments:razorpay_checkout", args=[self.invoice.pk]))
        return response

    def test_pay_button_only_when_configured(self):
        self.assertContains(self.client.get(reverse("invoicing:invoice_detail", args=[self.invoice.pk])), "Pay")
        with override_settings(RAZORPAY_ENABLED=False):
            self.assertNotContains(self.client.get(reverse("invoicing:invoice_detail", args=[self.invoice.pk])), "razorpay/checkout")

    def test_checkout_creates_order_for_outstanding_amount(self):
        response = self.start_checkout()
        self.assertEqual(response.status_code, 200)
        order = GatewayOrder.objects.get()
        self.assertEqual(order.amount, Decimal("500.00"))
        self.assertContains(response, "order_123")
        self.assertContains(response, "50000")

    def test_valid_callback_records_payment_and_marks_paid(self):
        self.start_checkout()
        order = GatewayOrder.objects.get()
        response = self.client.post(
            reverse("payments:razorpay_callback", args=[order.pk]),
            {"razorpay_order_id": "order_123", "razorpay_payment_id": "pay_1", "razorpay_signature": sign("secret", "order_123|pay_1")},
        )
        self.assertRedirects(response, reverse("invoicing:invoice_detail", args=[self.invoice.pk]))
        order.refresh_from_db(); self.invoice.refresh_from_db()
        self.assertEqual(order.status, "PAID")
        self.assertEqual(self.invoice.status, "PAID")
        self.assertEqual(Payment.objects.get().payment_method, "ONLINE")

    def test_bad_signature_records_nothing(self):
        self.start_checkout()
        order = GatewayOrder.objects.get()
        self.client.post(
            reverse("payments:razorpay_callback", args=[order.pk]),
            {"razorpay_order_id": "order_123", "razorpay_payment_id": "pay_1", "razorpay_signature": "forged"},
        )
        order.refresh_from_db()
        self.assertEqual(order.status, "FAILED")
        self.assertFalse(Payment.objects.exists())

    def test_other_customer_cannot_pay_or_callback(self):
        self.start_checkout()
        order = GatewayOrder.objects.get()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("payments:razorpay_checkout", args=[self.invoice.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("payments:razorpay_callback", args=[order.pk]), {}).status_code, 400)

    def test_webhook_settles_once_and_rejects_bad_signature(self):
        self.start_checkout()
        body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_9", "order_id": "order_123", "amount": 50000}}}}).encode()
        bad = self.client.post(reverse("payments:razorpay_webhook"), body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="nope")
        self.assertEqual(bad.status_code, 400)
        good = self.client.post(reverse("payments:razorpay_webhook"), body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=sign("whsecret", body))
        self.assertEqual(good.status_code, 200)
        self.client.post(reverse("payments:razorpay_webhook"), body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=sign("whsecret", body))
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(GatewayOrder.objects.get().status, "PAID")
