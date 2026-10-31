from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
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
            allow_early_close=False,
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

      
        with self.assertRaises(ValueError):
            self.service.activate(sub)

      
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
      
        with self.assertRaises(ValueError):
            self.service.close(sub)

      
        self.service.close(sub, force=True)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CLOSED)

    def test_number_is_unique_and_sequential(self):
        a = Subscription.objects.create(customer=self.customer, plan=self.plan)
        b = Subscription.objects.create(customer=self.customer, plan=self.plan)
        self.assertNotEqual(a.subscription_number, b.subscription_number)
        self.assertTrue(a.subscription_number.startswith("SUB-"))

    def test_customer_cannot_activate_or_edit(self):
        sub = Subscription.objects.create(customer=self.customer, plan=self.plan, status=Subscription.Status.CONFIRMED)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("subscriptions:detail", args=[sub.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("subscriptions:edit", args=[sub.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("subscriptions:action", args=[sub.pk, "activate"])).status_code, 403)
        other_user = User.objects.create_user(username="other", email="other@test.com", password="Password123!")
        other = CustomerProfile.objects.create(user=other_user, company_name="Other Co")
        other_sub = Subscription.objects.create(customer=other, plan=self.plan)
        self.assertEqual(self.client.get(reverse("subscriptions:detail", args=[other_sub.pk])).status_code, 404)

    def test_customer_subscribes_from_catalog(self):
        from apps.invoicing.models import Invoice

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("subscriptions:plans")).status_code, 200)
        response = self.client.post(
            reverse("subscriptions:subscribe", args=[self.plan.pk]),
            {
                "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "0", "lines-MAX_NUM_FORMS": "1000",
                "lines-0-product": self.product.pk, "lines-0-variant": "", "lines-0-quantity": "1", "payment_terms": "NET_15",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Subscription.objects.filter(customer=self.customer).exists())
        response = self.client.post(
            reverse("subscriptions:subscribe", args=[self.plan.pk]),
            {
                "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "0", "lines-MAX_NUM_FORMS": "1000",
                "lines-0-product": self.product.pk, "lines-0-variant": "", "lines-0-quantity": "3", "payment_terms": "NET_15",
            },
        )
        sub = Subscription.objects.get(customer=self.customer)
        invoice = Invoice.objects.get(subscription=sub)
        self.assertRedirects(response, reverse("invoicing:invoice_detail", args=[invoice.pk]))
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.total_amount, Decimal("300.00"))
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)
        self.assertEqual(invoice.subtotal, Decimal("300.00"))
        self.assertEqual(sub.next_billing_date, invoice.billing_period_end + timedelta(days=1))

    def test_staff_cannot_save_active_below_minimum_or_without_lines(self):
        staff = User.objects.create_user(username="s@test.com", email="s@test.com", password="Password123!", role="STAFF")
        self.client.force_login(staff)
        base = {"customer": self.customer.pk, "plan": self.plan.pk, "start_date": "2026-10-01", "expiry_date": "2026-09-01", "payment_terms": "NET_30", "status": "ACTIVE",
                "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "0", "lines-MAX_NUM_FORMS": "1000",
                "lines-0-product": "", "lines-0-variant": "", "lines-0-quantity": "1", "lines-0-unit_price": ""}
        response = self.client.post(reverse("subscriptions:create"), base)
        self.assertEqual(response.status_code, 200)
        self.assertIn("expiry_date", response.context["form"].errors)
        self.assertTrue(response.context["formset"].non_form_errors())
        base.update({"expiry_date": "2027-10-01", "lines-0-product": self.product.pk, "lines-0-quantity": "1"})
        response = self.client.post(reverse("subscriptions:create"), base)
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.context["form"].errors)
        base.update({"lines-0-quantity": "3"})
        response = self.client.post(reverse("subscriptions:create"), base)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Subscription.objects.get(customer=self.customer).status, "ACTIVE")

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
