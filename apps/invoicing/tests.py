from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomerProfile, User
from apps.discounts.models import Discount
from apps.invoicing.models import Invoice, InvoiceLine, InvoiceTaxLine
from apps.invoicing.services import InvoiceService, TaxService
from apps.plans.models import Plan
from apps.products.models import Product, Tax
from apps.subscriptions.models import Subscription, SubscriptionLine


class InvoicingTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()
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
        self.tax_18 = Tax.objects.create(name="GST 18%", rate=Decimal("18.00"), is_active=True)
        self.prod = Product.objects.create(name="SaaS Subscription Core", sales_price=Decimal("100.00"), tax=self.tax_18)
        self.plan = Plan.objects.create(
            name="Monthly Standard",
            billing_interval=Plan.BillingInterval.MONTHLY,
            price=Decimal("100.00"),
        )
        self.sub1 = Subscription.objects.create(
            subscription_number="SUB-CUST1-001",
            customer=self.cust_profile1,
            plan=self.plan,
            start_date=self.today - timedelta(days=30),
            next_billing_date=self.today,
            payment_terms=Subscription.PaymentTerms.NET_15,
            status=Subscription.Status.ACTIVE,
        )
        self.sub_line1 = SubscriptionLine.objects.create(
            subscription=self.sub1,
            product=self.prod,
            quantity=1,
        )
        self.assertEqual(self.sub_line1.tax_rate, Decimal("18.00"))
        self.assertEqual(self.sub_line1.amount, Decimal("100.00"))
        self.client = Client()

    def test_tax_math_and_rounding(self):
        tax_calc = TaxService.calculate_line_tax(Decimal("10.05"), Decimal("18.00"))
        self.assertEqual(tax_calc, Decimal("1.81"))
        tax_calc2 = TaxService.calculate_line_tax(Decimal("10.02"), Decimal("18.00"))
        self.assertEqual(tax_calc2, Decimal("1.80"))
        tax_zero = TaxService.calculate_line_tax(Decimal("100.00"), Decimal("0.00"))
        self.assertEqual(tax_zero, Decimal("0.00"))

    def test_idempotent_billing_single_subscription(self):
        period_start = self.today - timedelta(days=30)
        period_end = self.today - timedelta(days=1)
        inv1 = InvoiceService.generate_for_subscription(
            subscription=self.sub1,
            period_start=period_start,
            period_end=period_end,
        )
        self.assertIsNotNone(inv1)
        self.assertEqual(inv1.subtotal, Decimal("100.00"))
        self.assertEqual(inv1.tax_amount, Decimal("18.00"))
        self.assertEqual(inv1.total_amount, Decimal("118.00"))
        inv2 = InvoiceService.generate_for_subscription(
            subscription=self.sub1,
            period_start=period_start,
            period_end=period_end,
        )
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
        self.assertEqual(self.sub1.next_billing_date, self.today + relativedelta(months=1))
        invoice = result["invoices"][0]
        self.assertEqual(invoice.due_date, self.today + timedelta(days=15))
        self.assertEqual(invoice.billing_period_end, self.today + relativedelta(months=1) - timedelta(days=1))

        second = InvoiceService.generate_due_invoices(run_date=self.today)
        self.assertEqual(second["created"], 0)

    def test_status_transitions_and_validations(self):
        period_start = self.today - timedelta(days=60)
        period_end = self.today - timedelta(days=31)
        invoice = InvoiceService.generate_for_subscription(self.sub1, period_start, period_end)

        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        InvoiceService.confirm(invoice)
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)
        with self.assertRaises(ValidationError):
            InvoiceService.confirm(invoice)
        InvoiceService.mark_paid(invoice)
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        with self.assertRaises(ValidationError):
            InvoiceService.cancel(invoice)
        inv_cancel = InvoiceService.generate_for_subscription(
            self.sub1,
            self.today - timedelta(days=120),
            self.today - timedelta(days=91),
        )
        InvoiceService.cancel(inv_cancel)
        self.assertEqual(inv_cancel.status, Invoice.Status.CANCELLED)
        with self.assertRaises(ValidationError):
            InvoiceService.mark_paid(inv_cancel)

    def test_send_emails_invoice_with_pdf(self):
        from django.core import mail

        inv = InvoiceService.generate_for_subscription(self.sub1, self.today - timedelta(days=30), self.today - timedelta(days=1))
        InvoiceService.send(inv)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(inv.invoice_number, mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ["client1@domain.com"])
        name, content, mimetype = mail.outbox[0].attachments[0]
        self.assertEqual((name, mimetype), (f"{inv.invoice_number}.pdf", "application/pdf"))
        self.assertTrue(content.startswith(b"%PDF"))
        inv.refresh_from_db()
        self.assertIsNotNone(inv.sent_at)

    def test_pdf_view_for_owner_only(self):
        inv = InvoiceService.generate_for_subscription(self.sub1, self.today - timedelta(days=30), self.today - timedelta(days=1))
        self.client.force_login(self.cust_user1)
        response = self.client.get(reverse("invoicing:invoice_pdf", args=[inv.pk]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.client.force_login(self.cust_user2)
        self.assertEqual(self.client.get(reverse("invoicing:invoice_pdf", args=[inv.pk])).status_code, 404)

    def test_due_and_overdue_reminders(self):
        from django.core import mail
        from django.utils import timezone

        unsent = InvoiceService.generate_for_subscription(self.sub1, self.today - timedelta(days=30), self.today - timedelta(days=1))
        InvoiceService.confirm(unsent)
        Invoice.objects.filter(pk=unsent.pk).update(due_date=self.today + timedelta(days=2))
        overdue = InvoiceService.generate_for_subscription(self.sub1, self.today - timedelta(days=60), self.today - timedelta(days=31))
        InvoiceService.confirm(overdue)
        Invoice.objects.filter(pk=overdue.pk).update(due_date=self.today - timedelta(days=5), sent_at=timezone.now())
        draft = InvoiceService.generate_for_subscription(self.sub1, self.today - timedelta(days=90), self.today - timedelta(days=61))

        result = InvoiceService.send_due_notifications(today=self.today, days_before=3, repeat_days=7)
        self.assertEqual((result["invoice"], result["due"], result["overdue"]), (1, 1, 1))
        subjects = [m.subject for m in mail.outbox]
        self.assertTrue(any(s.startswith("Invoice ") for s in subjects))
        self.assertTrue(any(s.startswith("Reminder:") for s in subjects))
        self.assertTrue(any(s.startswith("Overdue:") for s in subjects))
        self.assertTrue(all(m.attachments for m in mail.outbox))

        mail.outbox.clear()
        again = InvoiceService.send_due_notifications(today=self.today, days_before=3, repeat_days=7)
        self.assertEqual((again["invoice"], again["due"], again["overdue"]), (0, 0, 0))
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Invoice.objects.get(pk=draft.pk).sent_at, None)

        later = InvoiceService.send_due_notifications(today=self.today + timedelta(days=8), days_before=3, repeat_days=7)
        self.assertEqual(later["overdue"], 2)

    def test_send_reminders_button_is_staff_only(self):
        self.client.force_login(self.cust_user1)
        self.assertEqual(self.client.post(reverse("invoicing:send_reminders")).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse("invoicing:send_reminders")).status_code, 302)

    def test_customer_cannot_see_others_invoices(self):
        inv1 = InvoiceService.generate_for_subscription(
            self.sub1,
            self.today - timedelta(days=30),
            self.today - timedelta(days=1),
        )
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
        self.client.force_login(self.cust_user1)
        res = self.client.get(reverse("invoicing:invoice_list"))
        self.assertEqual(res.status_code, 200)
        invoices_in_context = res.context["invoices"]
        self.assertIn(inv1, invoices_in_context)
        self.assertNotIn(inv2, invoices_in_context)
        res_own = self.client.get(reverse("invoicing:invoice_detail", args=[inv1.pk]))
        self.assertEqual(res_own.status_code, 200)
        res_other = self.client.get(reverse("invoicing:invoice_detail", args=[inv2.pk]))
        self.assertEqual(res_other.status_code, 404)

