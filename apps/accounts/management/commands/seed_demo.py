from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import CustomerProfile, User
from apps.discounts.models import Discount
from apps.invoicing.models import Invoice
from apps.invoicing.services import InvoiceService
from apps.payments.services import record_payment
from apps.plans.models import Plan
from apps.products.models import Product, ProductVariant, Tax
from apps.quotations.models import QuotationTemplate, QuotationTemplateLine
from apps.quotations.services import QuotationService
from apps.subscriptions.models import Subscription, SubscriptionLine
from apps.subscriptions.services import SubscriptionService

PASSWORD = "Brightloop!2026"
EMAIL_TEST_CUSTOMER = "milanpromod150@gmail.com"


class Command(BaseCommand):
    help = "Seed demo users, catalog, plans, templates, quotations, subscriptions, invoices and payments."

    def user(self, email, role, first="", last=""):
        user, created = User.objects.get_or_create(
            email=email, defaults={"username": email, "role": role, "first_name": first, "last_name": last}
        )
        if created:
            user.set_password(PASSWORD)
            user.save()
        return user

    def customer(self, email, company, phone, address, tax_number):
        user = self.user(email, User.Role.CUSTOMER)
        profile, _ = CustomerProfile.objects.get_or_create(
            user=user,
            defaults={"company_name": company, "phone": phone, "address": address, "tax_number": tax_number, "billing_email": email},
        )
        return profile

    def seed_email_test_customer(self, service, today, staff, plan, erp, support):
        customer = self.customer(EMAIL_TEST_CUSTOMER, "Anees Trading Co.", "+91 98765 43210", "14 MG Road, Kochi, Kerala", "IN-GST-32ABCDE1234F1Z5")
        if customer.subscriptions.exists():
            return
        due_sub = Subscription.objects.create(
            customer=customer, plan=plan, start_date=today - timedelta(days=70), expiry_date=today + timedelta(days=295),
            payment_terms="NET_15", status="CONFIRMED",
        )
        SubscriptionLine.objects.create(subscription=due_sub, product=erp, quantity=2)
        SubscriptionLine.objects.create(subscription=due_sub, product=support, quantity=1)
        service.activate(due_sub)
        due_sub.next_billing_date = today - timedelta(days=40)
        due_sub.save(update_fields=["next_billing_date"])
        InvoiceService.generate_due_invoices(run_date=today - timedelta(days=40))
        invoices = list(Invoice.objects.filter(subscription=due_sub).order_by("id"))
        for invoice in invoices:
            InvoiceService.confirm(invoice)
        if invoices:
            Invoice.objects.filter(pk=invoices[0].pk).update(issue_date=today - timedelta(days=40), due_date=today - timedelta(days=25))
        self.stdout.write(self.style.SUCCESS(
            f"Email test customer {EMAIL_TEST_CUSTOMER}: subscription {due_sub.subscription_number} is due for billing, "
            f"with {len(invoices)} confirmed invoice(s) awaiting email."
        ))

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()

        admin = self.user("admin@brightloop.com", User.Role.ADMIN, "Brightloop", "Admin")
        staff = self.user("alex@brightloop.com", User.Role.STAFF, "Alex", "Vance")
        self.user("priya@brightloop.com", User.Role.STAFF, "Priya", "Nair")

        apex = self.customer("ops@apexindustries.com", "Apex Industries Inc.", "+1 555 234 5678", "450 Industrial Parkway, Chicago, IL", "US-TAX-8921")
        brightcraft = self.customer("hello@brightcraft.io", "Brightcraft Studios", "+1 555 987 6543", "78 Creative Alley, Austin, TX", "US-TAX-4412")
        stellar = self.customer("billing@stellarlogistics.com", "Stellar Logistics LLC", "+1 555 345 6789", "900 Harbor Blvd, Seattle, WA", "US-TAX-7729")
        corner = self.customer("owner@cornershop.example", "Corner Shop Bakery", "+1 555 111 2222", "12 Main Street, Boise, ID", "")

        gst, _ = Tax.objects.get_or_create(name="Standard GST", defaults={"rate": Decimal("18.00"), "description": "Standard goods and services tax"})
        reduced, _ = Tax.objects.get_or_create(name="Reduced VAT", defaults={"rate": Decimal("5.00"), "description": "Reduced rate"})
        sales, _ = Tax.objects.get_or_create(name="Sales Tax", defaults={"rate": Decimal("10.00"), "description": "State sales tax"})
        Tax.objects.get_or_create(name="Zero Rate", defaults={"rate": Decimal("0.00"), "description": "Exports and exempt supplies"})

        erp, _ = Product.objects.get_or_create(
            name="Brightloop Business ERP",
            defaults={"product_type": "SOFTWARE", "sales_price": Decimal("1200.00"), "cost_price": Decimal("400.00"), "tax": gst, "notes": "Core ERP with inventory, accounting and sales."},
        )
        ProductVariant.objects.get_or_create(product=erp, attribute_name="Brand", attribute_value="Standard", defaults={"price_extra": Decimal("0.00")})
        odoo, _ = ProductVariant.objects.get_or_create(product=erp, attribute_name="Brand", attribute_value="Odoo", defaults={"price_extra": Decimal("560.00")})
        analytics, _ = Product.objects.get_or_create(
            name="Revenue Insights Analytics",
            defaults={"product_type": "SOFTWARE", "sales_price": Decimal("450.00"), "cost_price": Decimal("100.00"), "tax": gst, "notes": "Revenue and churn analytics."},
        )
        support, _ = Product.objects.get_or_create(
            name="24/7 Dedicated Support",
            defaults={"product_type": "SERVICE", "sales_price": Decimal("250.00"), "cost_price": Decimal("80.00"), "tax": sales, "notes": "One-hour SLA with a technical account manager."},
        )
        connector, _ = Product.objects.get_or_create(
            name="API & Webhook Connector",
            defaults={"product_type": "ADDON", "sales_price": Decimal("300.00"), "cost_price": Decimal("50.00"), "tax": reduced, "notes": "High-throughput API gateway add-on."},
        )
        seats, _ = Product.objects.get_or_create(
            name="Extra User Seat",
            defaults={"product_type": "ADDON", "sales_price": Decimal("45.00"), "cost_price": Decimal("5.00"), "tax": sales, "notes": "Additional named user."},
        )

        monthly, _ = Plan.objects.get_or_create(
            name="Business Monthly",
            defaults={"price": Decimal("180.00"), "billing_interval": "MONTHLY", "minimum_quantity": 2, "allow_pause": True, "allow_renewal": True, "allow_early_close": True, "auto_close": False},
        )
        yearly, _ = Plan.objects.get_or_create(
            name="Enterprise Annual",
            defaults={"price": Decimal("1800.00"), "billing_interval": "YEARLY", "minimum_quantity": 5, "allow_pause": False, "allow_renewal": True, "allow_early_close": False, "auto_close": False},
        )
        trial, _ = Plan.objects.get_or_create(
            name="Weekly Fast-Track Trial",
            defaults={"price": Decimal("49.00"), "billing_interval": "WEEKLY", "minimum_quantity": 1, "allow_pause": True, "allow_renewal": False, "allow_early_close": True, "auto_close": True},
        )
        daily, _ = Plan.objects.get_or_create(
            name="Daily Burst Capacity",
            defaults={"price": Decimal("25.00"), "billing_interval": "DAILY", "minimum_quantity": 1, "allow_pause": True, "allow_renewal": True, "allow_early_close": True, "auto_close": True},
        )

        for data in [
            {"name": "Welcome 20% Off", "discount_type": "PERCENTAGE", "value": Decimal("20.00"), "minimum_purchase": Decimal("500.00"), "start_date": today - timedelta(days=30), "end_date": today + timedelta(days=335), "usage_limit": 100, "applies_to": "SUBSCRIPTIONS"},
            {"name": "Volume Seats ₹150 Off", "discount_type": "FIXED", "value": Decimal("150.00"), "minimum_quantity": 5, "start_date": today - timedelta(days=10), "end_date": today + timedelta(days=180), "usage_limit": 50, "applies_to": "SUBSCRIPTIONS"},
            {"name": "Expired Flash Sale", "discount_type": "PERCENTAGE", "value": Decimal("30.00"), "start_date": today - timedelta(days=90), "end_date": today - timedelta(days=10), "usage_limit": 10, "applies_to": "SUBSCRIPTIONS"},
        ]:
            Discount.objects.get_or_create(name=data["name"], defaults={**data, "created_by": admin})
        support_discount, created = Discount.objects.get_or_create(
            name="Support Add-on 10% Off",
            defaults={"discount_type": "PERCENTAGE", "value": Decimal("10.00"), "start_date": today - timedelta(days=5), "end_date": today + timedelta(days=60), "applies_to": "PRODUCTS", "created_by": admin},
        )
        if created:
            support_discount.products.add(support)

        bundle, created = QuotationTemplate.objects.get_or_create(
            name="Standard Cloud ERP Bundle",
            defaults={"plan": monthly, "validity_days": 30, "created_by": staff, "description": "Core ERP with support for growing businesses."},
        )
        if created:
            QuotationTemplateLine.objects.create(template=bundle, product=erp, quantity=2)
            QuotationTemplateLine.objects.create(template=bundle, product=support, quantity=1)
        premium, created = QuotationTemplate.objects.get_or_create(
            name="Odoo Enterprise Premium",
            defaults={"plan": yearly, "validity_days": 45, "created_by": staff, "description": "Odoo brand edition with analytics and API connector."},
        )
        if created:
            QuotationTemplateLine.objects.create(template=premium, product=erp, variant=odoo, quantity=5)
            QuotationTemplateLine.objects.create(template=premium, product=analytics, quantity=1)
            QuotationTemplateLine.objects.create(template=premium, product=connector, quantity=1)

        service = SubscriptionService()
        self.seed_email_test_customer(service, today, staff, monthly, erp, support)

        if Subscription.objects.exclude(customer__user__email=EMAIL_TEST_CUSTOMER).exists():
            self.stdout.write(self.style.WARNING("Subscriptions already exist, skipping transactional demo data."))
            return

        def activate_with_billing(sub, days_ago):
            service.activate(sub)
            sub.next_billing_date = today - timedelta(days=days_ago)
            sub.save(update_fields=["next_billing_date"])

        q1 = QuotationService.create_from_template(bundle, apex, created_by=staff)
        QuotationService.send_quotation(q1)
        QuotationService.confirm_quotation(q1)
        sub1 = QuotationService.convert_to_subscription(q1)
        Subscription.objects.filter(pk=sub1.pk).update(start_date=today - timedelta(days=75), expiry_date=today + timedelta(days=290))
        sub1.refresh_from_db()
        activate_with_billing(sub1, 45)

        q2 = QuotationService.create_from_template(premium, brightcraft, created_by=staff, payment_terms="NET_15")
        QuotationService.send_quotation(q2)
        QuotationService.confirm_quotation(q2)
        sub2 = QuotationService.convert_to_subscription(q2)
        Subscription.objects.filter(pk=sub2.pk).update(start_date=today - timedelta(days=20), expiry_date=today + timedelta(days=345))
        sub2.refresh_from_db()
        activate_with_billing(sub2, 20)

        sub3 = Subscription.objects.create(customer=stellar, plan=monthly, start_date=today - timedelta(days=120), expiry_date=today + timedelta(days=245), payment_terms="NET_30", status="CONFIRMED")
        SubscriptionLine.objects.create(subscription=sub3, product=erp, quantity=2)
        SubscriptionLine.objects.create(subscription=sub3, product=seats, quantity=6)
        activate_with_billing(sub3, 90)

        sub4 = Subscription.objects.create(customer=stellar, plan=trial, start_date=today - timedelta(days=3), expiry_date=today + timedelta(days=4), payment_terms="IMMEDIATE", status="CONFIRMED")
        SubscriptionLine.objects.create(subscription=sub4, product=connector, quantity=1)

        sub5 = Subscription.objects.create(customer=corner, plan=monthly, start_date=today - timedelta(days=10), payment_terms="NET_15", status="DRAFT")
        SubscriptionLine.objects.create(subscription=sub5, product=erp, quantity=1)
        SubscriptionLine.objects.create(subscription=sub5, product=seats, quantity=2)

        sub6 = Subscription.objects.create(customer=corner, plan=daily, start_date=today - timedelta(days=40), expiry_date=today - timedelta(days=5), payment_terms="IMMEDIATE", status="CONFIRMED")
        SubscriptionLine.objects.create(subscription=sub6, product=seats, quantity=1)
        activate_with_billing(sub6, 5)

        sub7 = Subscription.objects.create(customer=apex, plan=monthly, start_date=today - timedelta(days=200), expiry_date=today + timedelta(days=160), payment_terms="NET_30", status="CONFIRMED")
        SubscriptionLine.objects.create(subscription=sub7, product=analytics, quantity=1)
        SubscriptionLine.objects.create(subscription=sub7, product=seats, quantity=3)
        service.activate(sub7)
        service.pause(sub7)

        q3 = QuotationService.create_from_template(bundle, corner, created_by=staff)
        QuotationService.send_quotation(q3)

        result = InvoiceService.generate_due_invoices(run_date=today)
        invoices = list(Invoice.objects.order_by("id"))
        for invoice in invoices:
            InvoiceService.confirm(invoice)
        if invoices:
            Invoice.objects.filter(pk=invoices[0].pk).update(issue_date=today - timedelta(days=45), due_date=today - timedelta(days=15))
            invoices[0].refresh_from_db()
            record_payment(invoices[0], invoices[0].total_amount, "BANK_TRANSFER", staff, payment_date=timezone.now() - timedelta(days=20), notes="Wire transfer")
        if len(invoices) > 1:
            Invoice.objects.filter(pk=invoices[1].pk).update(issue_date=today - timedelta(days=40), due_date=today - timedelta(days=10))
            invoices[1].refresh_from_db()
            record_payment(invoices[1], (invoices[1].total_amount / 2).quantize(Decimal("0.01")), "CARD", staff, payment_date=timezone.now() - timedelta(days=8), notes="First instalment")
        if len(invoices) > 2:
            record_payment(invoices[2], invoices[2].total_amount, "UPI", staff, payment_date=timezone.now() - timedelta(days=2))

        self.stdout.write(self.style.SUCCESS(
            f"Seeded demo data. Invoices created: {result['created']}. "
            f"Sign in with admin@brightloop.com, alex@brightloop.com, ops@apexindustries.com or {EMAIL_TEST_CUSTOMER} and password {PASSWORD}"
        ))
