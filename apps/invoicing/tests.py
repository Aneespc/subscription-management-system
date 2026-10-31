from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomerProfile, User
from apps.discounts.models import Discount
from apps.invoicing.models import Invoice, InvoiceLine, InvoiceTaxLine, Tax
from apps.invoicing.services import InvoiceService, TaxService
from apps.plans.models import Plan
from apps.products.models import Product
from apps.subscriptions.models import Subscription, SubscriptionLine


class InvoicingTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()

        # Users & Roles
        self.admin = User.objects.create_superuser(
            username="admin_user",
            email="admin@brightloop.com",
            password="pass",
            role=User.Role.ADMIN,
        )
        self.staff = User.objects.create_user(
            username="staff_user",
            email="staff@brightloop.com",
            password="pass",
            role=User.Role.STAFF,
        )
        self.cust_user1 = User.objects.create_user(
            username="client_one",
            email="client1@domain.com",
            password="pass",
            role=User.Role.CUSTOMER,
        )
        self.cust_profile1 = CustomerProfile.objects.create(
            user=self.cust_user1,
            company_name="Client One Corp",
            billing_email="client1@domain.com",
        )
        self.cust_user2 = User.objects.create_user(
            username="client_two",
            email="client2@domain.com",
            password="pass",
            role=User.Role.CUSTOMER,
        )
        self.cust_profile2 = CustomerProfile.objects.create(
            user=self.cust_user2,
            company_name="Client Two LLC",
            billing_email="client2@domain.com",
        )

        # Products & Plan
        self.prod = Product.objects.create(
            name="SaaS Subscription Core",
            sku="CORE-01",
            unit_price=Decimal("100.00"),
        )
        self.plan = Plan.objects.create(
            name="Monthly Standard",
            billing_interval=Plan.BillingInterval.MONTHLY,
            billing_interval_count=1,
            price=Decimal("100.00"),
        )

        # Subscriptions
        self.sub1 = Subscription.objects.create(
            subscription_number="SUB-CUST1-001",
            customer=self.cust_profile1,
            plan=self.plan,
            start_date=self.today - timedelta(days=30),
            next_billing_date=self.today,
            payment_terms=15,
            status=Subscription.Status.ACTIVE,
        )
        self.sub_line1 = SubscriptionLine.objects.create(
            subscription=self.sub1,
            product=self.prod,
            quantity=1,
            unit_price=Decimal("100.00"),
            tax_rate=Decimal("18.00"),
            amount=Decimal("100.00"),
        )

        # Taxes
        self.tax_18 = Tax.objects.create(
            name="GST 18%",
            rate=Decimal("18.00"),
            is_active=True,
        )
        self.client = Client()

    def test_tax_math_and_rounding(self):
        # Test ROUND_HALF_UP behavior
        # $10.05 * 18% = 1.8090 -> rounds to $1.81
        tax_calc = TaxService.calculate_line_tax(Decimal("10.05"), Decimal("18.00"))
        self.assertEqual(tax_calc, Decimal("1.81"))

        # $10.02 * 18% = 1.8036 -> rounds to $1.80
        tax_calc2 = TaxService.calculate_line_tax(Decimal("10.02"), Decimal("18.00"))
        self.assertEqual(tax_calc2, Decimal("1.80"))

        # Zero tax rate
        tax_zero = TaxService.calculate_line_tax(Decimal("100.00"), Decimal("0.00"))
        self.assertEqual(tax_zero, Decimal("0.00"))

    def test_idempotent_billing_single_subscription(self):
        period_start = self.today - timedelta(days=30)
        period_end = self.today - timedelta(days=1)

        # Generate invoice for the first time
        inv1 = InvoiceService.generate_for_subscription(
            subscription=self.sub1,
            period_start=period_start,
            period_end=period_end,
        )
        self.assertIsNotNone(inv1)
        self.assertEqual(inv1.subtotal, Decimal("100.00"))
        self.assertEqual(inv1.tax_amount, Decimal("18.00"))
        self.assertEqual(inv1.total_amount, Decimal("118.00"))

        # Generate for the exact same subscription & period a second time
        inv2 = InvoiceService.generate_for_subscription(
            subscription=self.sub1,
            period_start=period_start,
            period_end=period_end,
        )
        # Must return the identical instance without creating a duplicate record
        self.assertEqual(inv1.pk, inv2.pk)
        self.assertEqual(inv1.invoice_number, inv2.invoice_number)
        self.assertEqual(
            Invoice.objects.filter(
                subscription=self.sub1,
                billing_period_start=period_start,
                billing_period_end=period_end,
            ).count(),
            1,
        )

    def test_batch_generate_due_invoices_advances_date(self):
        result = InvoiceService.generate_due_invoices(run_date=self.today)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["failed"], 0)

        self.sub1.refresh_from_db()
        # Next billing date should have advanced by 1 month
        expected_next = self.today + timedelta(days=31)  # Or relativedelta(months=1)
        self.assertTrue(self.sub1.next_billing_date > self.today)

    def test_status_transitions_and_validations(self):
        period_start = self.today - timedelta(days=60)
        period_end = self.today - timedelta(days=31)
        invoice = InvoiceService.generate_for_subscription(self.sub1, period_start, period_end)

        self.assertEqual(invoice.status, Invoice.Status.DRAFT)

        # 1. Confirm: DRAFT -> CONFIRMED
        InvoiceService.confirm(invoice)
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

        # Re-confirming an already confirmed invoice raises ValidationError
        with self.assertRaises(ValidationError):
            InvoiceService.confirm(invoice)

        # 2. Mark Paid: CONFIRMED -> PAID
        InvoiceService.mark_paid(invoice)
        self.assertEqual(invoice.status, Invoice.Status.PAID)

        # 3. Attempting to cancel a PAID invoice must fail with ValidationError
        with self.assertRaises(ValidationError):
            InvoiceService.cancel(invoice)

        # 4. Create new draft invoice and test CANCELLED flow
        inv_cancel = InvoiceService.generate_for_subscription(
            self.sub1,
            self.today - timedelta(days=120),
            self.today - timedelta(days=91),
        )
        InvoiceService.cancel(inv_cancel)
        self.assertEqual(inv_cancel.status, Invoice.Status.CANCELLED)

        # Cannot mark a cancelled invoice as PAID
        with self.assertRaises(ValidationError):
            InvoiceService.mark_paid(inv_cancel)

    def test_customer_cannot_see_others_invoices(self):
        # Create an invoice belonging to Customer 1
        inv1 = InvoiceService.generate_for_subscription(
            self.sub1,
            self.today - timedelta(days=30),
            self.today - timedelta(days=1),
        )

        # Create subscription & invoice for Customer 2
        sub2 = Subscription.objects.create(
            subscription_number="SUB-CUST2-001",
            customer=self.cust_profile2,
            plan=self.plan,
            start_date=self.today - timedelta(days=30),
            next_billing_date=self.today,
            status=Subscription.Status.ACTIVE,
        )
        SubscriptionLine.objects.create(
            subscription=sub2,
            product=self.prod,
            quantity=1,
            unit_price=Decimal("100.00"),
            amount=Decimal("100.00"),
        )
        inv2 = InvoiceService.generate_for_subscription(
            sub2,
            self.today - timedelta(days=30),
            self.today - timedelta(days=1),
        )

        # Log in as Customer 1
        self.client.force_login(self.cust_user1)

        # Customer 1 list view should only show Customer 1's invoice
        res = self.client.get(reverse("invoicing:invoice_list"))
        self.assertEqual(res.status_code, 200)
        invoices_in_context = res.context["invoices"]
        self.assertIn(inv1, invoices_in_context)
        self.assertNotIn(inv2, invoices_in_context)

        # Customer 1 accessing Customer 1's invoice detail -> 200 OK
        res_own = self.client.get(reverse("invoicing:invoice_detail", args=[inv1.pk]))
        self.assertEqual(res_own.status_code, 200)

        # Customer 1 attempting to access Customer 2's invoice detail -> 403 Forbidden
        res_other = self.client.get(reverse("invoicing:invoice_detail", args=[inv2.pk]))
        self.assertEqual(res_other.status_code, 403)

    def test_pdf_rendering(self):
        inv = InvoiceService.generate_for_subscription(
            self.sub1,
            self.today - timedelta(days=30),
            self.today - timedelta(days=1),
        )
        pdf_bytes = InvoiceService.render_pdf(inv)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

