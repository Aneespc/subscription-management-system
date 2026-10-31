import threading
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from .models import Invoice, Payment
from .services import (PaymentError, calculate_outstanding, get_overdue_invoices,
                       get_payable_invoices, record_payment)

User = get_user_model()


def make_user(username, staff=False):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com",
        password="Passw0rd!x", is_staff=staff,
    )


def make_invoice(number, total="1000.00", status=Invoice.Status.CONFIRMED, due_in_days=10):
    return Invoice.objects.create(
        invoice_number=number, total_amount=Decimal(total), status=status,
        due_date=date.today() + timedelta(days=due_in_days),
    )


class PaymentServiceTests(TestCase):
    def setUp(self):
        self.staff = make_user("staff", staff=True)
        self.invoice = make_invoice("INV-1")

    def pay(self, amount, method="CASH"):
        return record_payment(self.invoice, amount, method, self.staff)

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
        self.assertEqual(Payment.objects.count(), 0)

    def test_draft_and_cancelled_invoices_reject_payments(self):
        for status in (Invoice.Status.DRAFT, Invoice.Status.CANCELLED):
            self.invoice.status = status
            self.invoice.save()
            with self.assertRaises(PaymentError):
                self.pay("100")

    def test_zero_negative_and_unknown_method_rejected(self):
        for amount in ("0", "-5"):
            with self.assertRaises(PaymentError):
                self.pay(amount)
        with self.assertRaises(PaymentError):
            self.pay("100", method="BITCOIN")

    def test_payment_numbers_are_unique(self):
        first = self.pay("100")
        second = self.pay("100")
        self.assertNotEqual(first.payment_number, second.payment_number)
        self.assertTrue(first.payment_number.startswith("PAY-"))

    def test_overdue_detection(self):
        self.invoice.due_date = date.today() - timedelta(days=1)
        self.invoice.save()
        self.assertEqual(get_overdue_invoices().count(), 1)
        self.pay("1000")
        self.assertEqual(get_overdue_invoices().count(), 0)

    def test_payable_invoices_excludes_paid_and_draft(self):
        make_invoice("INV-DRAFT", status=Invoice.Status.DRAFT)
        paid = make_invoice("INV-PAID", total="50.00")
        record_payment(paid, "50", "CASH", self.staff)
        numbers = list(get_payable_invoices().values_list("invoice_number", flat=True))
        self.assertEqual(numbers, ["INV-1"])


class PaymentAPITests(TestCase):
    def setUp(self):
        self.staff = make_user("staff", staff=True)
        self.outsider = make_user("outsider")
        self.invoice = make_invoice("INV-1")
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def post_payment(self, amount, **extra):
        data = {"invoice": self.invoice.pk, "amount": amount, "payment_method": "CASH", **extra}
        return self.api.post("/api/payments/", data, format="json")

    def test_staff_can_record_a_payment(self):
        response = self.post_payment("400", transaction_reference="REF1", notes="first part")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body["payment_number"].startswith("PAY-"))
        self.assertEqual(body["invoice_number"], "INV-1")

        outstanding = self.api.get(f"/api/invoices/{self.invoice.pk}/outstanding/").json()
        self.assertEqual(Decimal(outstanding["outstanding"]), Decimal("600.00"))
        self.assertEqual(Decimal(outstanding["total_paid"]), Decimal("400.00"))

    def test_paying_the_full_balance_marks_invoice_paid(self):
        self.post_payment("1000")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

    def test_overpayment_returns_400_with_a_message(self):
        response = self.post_payment("1000.01")
        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds", response.json()["detail"][0])

    def test_draft_invoice_returns_400(self):
        self.invoice.status = Invoice.Status.DRAFT
        self.invoice.save()
        self.assertEqual(self.post_payment("100").status_code, 400)

    def test_invalid_input_returns_400(self):
        self.assertEqual(self.post_payment("abc").status_code, 400)
        bad_method = self.api.post(
            "/api/payments/",
            {"invoice": self.invoice.pk, "amount": "10", "payment_method": "BITCOIN"},
            format="json",
        )
        self.assertEqual(bad_method.status_code, 400)

    def test_non_staff_users_are_forbidden(self):
        self.api.force_authenticate(self.outsider)
        self.assertEqual(self.api.get("/api/payments/").status_code, 403)
        self.assertEqual(self.post_payment("100").status_code, 403)
        self.assertEqual(self.api.get("/api/invoices/overdue/").status_code, 403)

    def test_anonymous_users_are_blocked(self):
        self.api.force_authenticate(None)
        self.assertIn(self.api.get("/api/payments/").status_code, (401, 403))

    def test_superuser_is_allowed(self):
        admin = User.objects.create_superuser(
            username="root", email="root@example.com", password="Passw0rd!x"
        )
        self.api.force_authenticate(admin)
        self.assertEqual(self.api.get("/api/payments/").status_code, 200)

    def test_list_filters_and_detail(self):
        record_payment(self.invoice, "100", "CASH", self.staff)
        upi = record_payment(self.invoice, "200", "UPI", self.staff)
        self.assertEqual(self.api.get("/api/payments/").json()["count"], 2)
        self.assertEqual(self.api.get("/api/payments/?method=UPI").json()["count"], 1)
        self.assertEqual(self.api.get(f"/api/payments/?invoice={self.invoice.pk}").json()["count"], 2)
        detail = self.api.get(f"/api/payments/{upi.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["payment_method"], "UPI")

    def test_payments_cannot_be_edited_or_deleted(self):
        payment = record_payment(self.invoice, "100", "CASH", self.staff)
        self.assertEqual(self.api.delete(f"/api/payments/{payment.pk}/").status_code, 405)
        self.assertEqual(self.api.put(f"/api/payments/{payment.pk}/", {}, format="json").status_code, 405)

    def test_payments_for_one_invoice(self):
        record_payment(self.invoice, "100", "CASH", self.staff)
        body = self.api.get(f"/api/invoices/{self.invoice.pk}/payments/").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(self.api.get("/api/invoices/99999/payments/").status_code, 404)

    def test_overdue_endpoint(self):
        late = make_invoice("INV-LATE", total="300.00", due_in_days=-10)
        record_payment(late, "100", "CASH", self.staff)
        body = self.api.get("/api/invoices/overdue/").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["invoice_number"], "INV-LATE")
        self.assertEqual(Decimal(body["results"][0]["outstanding"]), Decimal("200.00"))

    def test_payable_endpoint_and_search(self):
        make_invoice("INV-DRAFT", status=Invoice.Status.DRAFT)
        body = self.api.get("/api/invoices/payable/").json()
        self.assertEqual([r["invoice_number"] for r in body["results"]], ["INV-1"])
        self.assertEqual(self.api.get("/api/invoices/payable/?search=INV-1").json()["count"], 1)
        self.assertEqual(self.api.get("/api/invoices/payable/?search=zzz").json()["count"], 0)


class ConcurrentPaymentTests(TransactionTestCase):
    """Needs PostgreSQL: SQLite ignores select_for_update, so it can't prove the locking."""

    def test_two_simultaneous_payments_cannot_overpay(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row locking can only be tested on PostgreSQL.")

        staff = make_user("staff", staff=True)
        invoice = make_invoice("INV-RACE", total="1000.00")
        barrier = threading.Barrier(2)
        results = []

        def worker():
            try:
                barrier.wait()
                record_payment(invoice, "600", "CASH", staff)
                results.append("ok")
            except PaymentError:
                results.append("rejected")
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(results), ["ok", "rejected"])
        self.assertEqual(Payment.objects.filter(invoice=invoice).count(), 1)