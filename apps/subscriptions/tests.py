from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from apps.accounts.models import User, CustomerProfile
from apps.products.models import Product
from apps.plans.models import Plan
from apps.subscriptions.models import Subscription, SubscriptionLine
from apps.subscriptions.services import SubscriptionService


class SubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cust1", email="cust@test.com", password="Password123!")
        self.customer = CustomerProfile.objects.create(user=self.user, company_name="Acme Corp")
        self.plan = Plan.objects.create(
            name="Pro Monthly",
            price=Decimal("150.00"),
            billing_interval="MONTHLY",
            minimum_quantity=3,
            allow_pause=True,
            allow_renewal=True,
            allow_early_close=False,  # Disallows early close
            auto_close=True
        )
        self.product = Product.objects.create(name="App Suite", sales_price=Decimal("100.00"))
        self.service = SubscriptionService()

    def test_activate_respects_minimum_quantity(self):
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.Status.CONFIRMED
        )
        SubscriptionLine.objects.create(subscription=sub, product=self.product, quantity=1, unit_price=Decimal("100.00"), amount=Decimal("100.00"))

        # Should fail because min_quantity is 3 and quantity is 1
        with self.assertRaises(ValueError):
            self.service.activate(sub)

        # Now add 2 more seats to reach 3
        SubscriptionLine.objects.create(subscription=sub, product=self.product, quantity=2, unit_price=Decimal("100.00"), amount=Decimal("200.00"))
        self.service.activate(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertIsNotNone(sub.next_billing_date)

    def test_pause_and_resume(self):
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.Status.ACTIVE
        )
        self.service.pause(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.PAUSED)

        self.service.resume(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)

    def test_close_policy_enforcement(self):
        today = timezone.now().date()
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.Status.ACTIVE,
            expiry_date=today + timedelta(days=90)
        )
        # Because plan.allow_early_close is False, early closing should fail
        with self.assertRaises(ValueError):
            self.service.close(sub)

        # Force closing works
        self.service.close(sub, force=True)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CLOSED)

    def test_renew(self):
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.Status.ACTIVE,
            expiry_date=timezone.now().date() + timedelta(days=10)
        )
        initial_expiry = sub.expiry_date
        self.service.renew(sub, additional_days=30)
        sub.refresh_from_db()
        self.assertEqual(sub.expiry_date, initial_expiry + timedelta(days=30))
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
