from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from apps.accounts.models import User, CustomerProfile
from apps.products.models import Product, ProductVariant
from apps.plans.models import Plan
from apps.quotations.models import Quotation, QuotationLine, QuotationTemplate, QuotationTemplateLine
from apps.quotations.services import QuotationService
from apps.subscriptions.models import Subscription


class QuotationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="rep1", email="rep@test.com", password="Password123!")
        self.customer = CustomerProfile.objects.create(user=self.user, company_name="Test Enterprise")
        self.plan = Plan.objects.create(name="Test Monthly Plan", price=Decimal("100.00"), billing_interval="MONTHLY", minimum_quantity=2)
        self.product = Product.objects.create(name="ERP Pro", sales_price=Decimal("500.00"), product_type="SOFTWARE")
        self.variant = ProductVariant.objects.create(product=self.product, attribute_name="Brand", attribute_value="Odoo", price_extra=Decimal("560.00"))

    def test_quotation_creation_and_recalculation(self):
        quote = Quotation.objects.create(
            customer=self.customer,
            issue_date=timezone.now().date(),
            expiry_date=timezone.now().date() + timedelta(days=30),
            payment_terms=Quotation.PaymentTerms.NET_30
        )
        line = QuotationLine.objects.create(
            quotation=quote,
            product=self.product,
            variant=self.variant,
            quantity=2,
            unit_price=Decimal("1060.00"),  # 500 + 560
            tax_rate=Decimal("10.00")
        )
        QuotationService.recalculate_totals(quote)
        quote.refresh_from_db()

        self.assertEqual(quote.subtotal, Decimal("2120.00"))
        self.assertEqual(quote.tax_amount, Decimal("212.00"))
        self.assertEqual(quote.total_amount, Decimal("2332.00"))

    def test_create_from_template_and_convert_to_subscription(self):
        template = QuotationTemplate.objects.create(
            name="ERP Bundle",
            plan=self.plan,
            validity_days=15
        )
        QuotationTemplateLine.objects.create(template=template, product=self.product, variant=self.variant, quantity=3)

        quote = QuotationService.create_from_template(template, self.customer)
        self.assertEqual(quote.lines.count(), 1)
        self.assertEqual(quote.template, template)
        self.assertEqual(quote.expiry_date, quote.issue_date + timedelta(days=15))

        # Confirm and convert
        QuotationService.confirm_quotation(quote)
        self.assertEqual(quote.status, Quotation.Status.CONFIRMED)

        sub = QuotationService.convert_to_subscription(quote)
        self.assertIsNotNone(sub)
        self.assertEqual(sub.customer, self.customer)
        self.assertEqual(sub.plan, self.plan)
        self.assertEqual(sub.lines.count(), 1)
        self.assertEqual(quote.status, Quotation.Status.CONVERTED)
