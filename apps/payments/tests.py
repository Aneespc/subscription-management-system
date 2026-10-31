from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Invoice
from .services import PaymentError, calculate_outstanding, get_overdue_invoices, record_payment


class PaymentServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="staff", password="x")
        self.invoice = Invoice.objects.create(
            invoice_number="INV-1", total_amount=Decimal("1000.00"),
            status=Invoice.Status.CONFIRMED, due_date=date.today() + timedelta(days=10),
        )

    def pay(self, amount):
        return record_payment(self.invoice, amount, "CASH", self.user)

    def test_partial_payment_keeps_invoice_confirmed(self):
        self.pay("400")
        self.invoice.refresh_from_db()
        self.assertEqual(calculate_outstanding(self.invoice), Decimal("600.00"))
        self.assertEqual(self.invoice.status, Invoice.Status.CONFIRMED)

    def test_full_payment_marks_paid(self):
        self.pay("400")
        self.pay("600")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

    def test_overpayment_rejected(self):
        with self.assertRaises(PaymentError):
            self.pay("1000.01")

    def test_draft_invoice_rejected(self):
        self.invoice.status = Invoice.Status.DRAFT
        self.invoice.save()
        with self.assertRaises(PaymentError):
            self.pay("100")

    def test_overdue_detection(self):
        self.invoice.due_date = date.today() - timedelta(days=1)
        self.invoice.save()
        self.assertEqual(get_overdue_invoices().count(), 1)
        self.pay("1000")
        self.assertEqual(get_overdue_invoices().count(), 0)