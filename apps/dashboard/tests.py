from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomerProfile, User
from apps.plans.models import Plan
from apps.products.models import Product
from apps.subscriptions.models import Subscription, SubscriptionLine

from .services import get_summary


class DashboardTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="s@x.com", email="s@x.com", password="Str0ng!Pass", role="STAFF")
        user = User.objects.create_user(username="c@x.com", email="c@x.com", password="Str0ng!Pass")
        customer = CustomerProfile.objects.create(user=user, company_name="C")
        product = Product.objects.create(name="P", sales_price=Decimal("120.00"))
        monthly = Plan.objects.create(name="M", billing_interval="MONTHLY")
        s1 = Subscription.objects.create(customer=customer, plan=monthly, status="ACTIVE")
        s2 = Subscription.objects.create(customer=customer, plan=monthly, status="PAUSED")
        SubscriptionLine.objects.create(subscription=s1, product=product, quantity=1)
        SubscriptionLine.objects.create(subscription=s2, product=product, quantity=10)

    def test_summary_counts(self):
        summary = get_summary({})
        self.assertEqual(summary["active_subscriptions"], 1)
        self.assertEqual(summary["total_subscriptions"], 2)
        self.assertEqual(summary["total_customers"], 1)

    def test_dashboard_page_with_filters(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 200)
        response = self.client.get(reverse("dashboard:index"), {"date_from": "2026-01-01", "method": "CARD"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["summary"]["payments_count"], 0)
