from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Sum
from django.test import TestCase
from rest_framework.test import APIClient

from apps.payments.models import Invoice, Payment
from apps.payments.services import record_payment

User = get_user_model()


def make_user(username, staff=False):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com",
        password="Passw0rd!x", is_staff=staff,
    )


def make_invoice(number, total, status=Invoice.Status.CONFIRMED, due_in_days=10):
    return Invoice.objects.create(
        invoice_number=number, total_amount=Decimal(total), status=status,
        due_date=date.today() + timedelta(days=due_in_days),
    )


class DashboardTests(TestCase):
    """Known data: payments 400 CASH + 100 UPI + 250 CARD = 750.

    A  1000 due in 10 days, paid 400  -> owes 600 (not overdue)
    B   500 overdue 5 days, unpaid    -> owes 500
    C   300 overdue 40 days, paid 100 -> owes 200
    D   200 overdue 100 days, unpaid  -> owes 200
    E   250 fully paid                -> PAID
    F   999 draft                     -> ignored
    """

    def setUp(self):
        cache.clear()
        self.staff = make_user("staff", staff=True)
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

        self.a = make_invoice("INV-A", "1000.00", due_in_days=10)
        make_invoice("INV-B", "500.00", due_in_days=-5)
        self.c = make_invoice("INV-C", "300.00", due_in_days=-40)
        make_invoice("INV-D", "200.00", due_in_days=-100)
        self.e = make_invoice("INV-E", "250.00", due_in_days=-3)
        make_invoice("INV-F", "999.00", status=Invoice.Status.DRAFT)

        record_payment(self.a, "400", "CASH", self.staff)
        record_payment(self.c, "100", "UPI", self.staff)
        record_payment(self.e, "250", "CARD", self.staff)

    def get(self, url):
        response = self.api.get(url)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_summary_totals_match_raw_data(self):
        summary = self.get("/api/dashboard/summary/")
        raw_total = Payment.objects.aggregate(t=Sum("amount"))["t"]
        self.assertEqual(Decimal(summary["revenue_received"]), raw_total)
        self.assertEqual(Decimal(summary["revenue_received"]), Decimal("750.00"))
        self.assertEqual(summary["payments_count"], 3)
        self.assertEqual(Decimal(summary["outstanding_amount"]), Decimal("1500.00"))
        self.assertEqual(summary["overdue_invoices"], 3)
        self.assertEqual(Decimal(summary["overdue_amount"]), Decimal("900.00"))
        self.assertEqual(summary["total_invoices"], 6)

    def test_filters(self):
        self.assertEqual(Decimal(self.get("/api/dashboard/summary/?method=CASH")["revenue_received"]), Decimal("400.00"))
        self.assertEqual(Decimal(self.get("/api/dashboard/summary/?method=UPI")["revenue_received"]), Decimal("100.00"))
        self.assertEqual(Decimal(self.get("/api/dashboard/summary/?invoice_status=PAID")["revenue_received"]), Decimal("250.00"))
        future = self.get("/api/dashboard/summary/?date_from=2999-01-01")
        self.assertEqual(Decimal(future["revenue_received"]), Decimal("0.00"))
        self.assertEqual(future["payments_count"], 0)

    def test_bad_date_returns_400(self):
        self.assertEqual(self.api.get("/api/dashboard/summary/?date_from=13/45").status_code, 400)

    def test_revenue_grouping(self):
        for group in ("month", "quarter", "year"):
            body = self.get(f"/api/dashboard/revenue/?group={group}")
            self.assertEqual(body["group"], group)
            self.assertEqual(len(body["results"]), 1)
            self.assertEqual(Decimal(body["results"][0]["total"]), Decimal("750.00"))

    def test_payments_by_method(self):
        report = self.get("/api/dashboard/reports/")
        by_method = {m["payment_method"]: Decimal(m["total"]) for m in report["payments_by_method"]}
        self.assertEqual(by_method, {"CASH": Decimal("400.00"), "UPI": Decimal("100.00"), "CARD": Decimal("250.00")})

    def test_overdue_invoices_are_sorted_oldest_first(self):
        body = self.get("/api/dashboard/overdue-invoices/")
        self.assertEqual(body["count"], 3)
        self.assertEqual([r["invoice_number"] for r in body["results"]], ["INV-D", "INV-C", "INV-B"])
        self.assertEqual(Decimal(body["results"][1]["outstanding"]), Decimal("200.00"))

    def test_aging_buckets(self):
        aging = self.get("/api/dashboard/aging/")
        buckets = {b["bucket"]: b for b in aging["buckets"]}
        self.assertEqual(Decimal(buckets["1-30 days"]["amount"]), Decimal("500.00"))
        self.assertEqual(Decimal(buckets["31-60 days"]["amount"]), Decimal("200.00"))
        self.assertEqual(buckets["61-90 days"]["count"], 0)
        self.assertEqual(Decimal(buckets["90+ days"]["amount"]), Decimal("200.00"))
        self.assertEqual(aging["total_count"], 3)
        self.assertEqual(Decimal(aging["total_amount"]), Decimal("900.00"))

    def test_non_staff_cannot_read_the_dashboard(self):
        self.api.force_authenticate(make_user("outsider"))
        for url in ("/api/dashboard/summary/", "/api/dashboard/aging/", "/api/dashboard/reports/"):
            self.assertEqual(self.api.get(url).status_code, 403)

    def test_summary_refreshes_after_a_new_payment(self):
        before = Decimal(self.get("/api/dashboard/summary/")["revenue_received"])
        with self.captureOnCommitCallbacks(execute=True):
            record_payment(self.a, "100", "CASH", self.staff)
        after = Decimal(self.get("/api/dashboard/summary/")["revenue_received"])
        self.assertEqual(after - before, Decimal("100.00"))


class DashboardPageTests(TestCase):
    def test_anonymous_is_redirected_to_login(self):
        self.assertEqual(self.client.get("/dashboard/").status_code, 302)

    def test_staff_sees_the_page_with_the_payment_form(self):
        self.client.force_login(make_user("staff", staff=True))
        response = self.client.get("/dashboard/")
        self.assertContains(response, "Finance Dashboard")
        self.assertContains(response, "csrfmiddlewaretoken")