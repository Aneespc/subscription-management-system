from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import CustomerProfile
from apps.invoicing.models import Invoice

from .services import PaymentError, calculate_outstanding, get_overdue_invoices, record_payment

User = get_user_model()


class PaymentServiceTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff", email="staff@example.com", password="Passw0rd!x", role="STAFF"
        )
        customer_user = User.objects.create_user(
            username="cust", email="cust@example.com", password="Passw0rd!x", role="CUSTOMER"
        )
        self.customer = CustomerProfile.objects.create(
            user=customer_user, company_name="Test Co", phone="0000000000", address="Test address"
        )
        self.invoice = self.make_invoice("INV-1", due_in_days=10)

    def make_invoice(self, number, due_in_days):
        due = date.today() + timedelta(days=due_in_days)
        return Invoice.objects.create(
            invoice_number=number, customer=self.customer,
            total_amount=Decimal("1000.00"), status=Invoice.Status.CONFIRMED,
            due_date=due, billing_period_start=due - timedelta(days=30), billing_period_end=due,
        )

    def pay(self, amount):
        return record_payment(self.invoice, amount, "CASH", self.staff)

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