from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import CustomerProfile, User
from apps.discounts.models import Discount, DiscountUsage
from apps.discounts.services import DiscountService
from apps.invoicing.models import Invoice
from apps.plans.models import Plan
from apps.products.models import Product
from apps.subscriptions.models import Subscription, SubscriptionLine


class DiscountModelAndServiceTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()
        self.admin = User.objects.create_superuser(
            username="admin_test",
            email="admin@test.com",
            password="pass",
            role=User.Role.ADMIN,
        )
        self.user = User.objects.create_user(
            username="cust_test",
            email="cust@test.com",
            password="pass",
            role=User.Role.CUSTOMER,
        )
        self.customer = CustomerProfile.objects.create(
            user=self.user,
            company_name="Test Customer Co",
            billing_email="cust@test.com",
        )
        self.prod1 = Product.objects.create(
            name="Cloud Plan Pro",
            sku="SKU-PRO",
            unit_price=Decimal("100.00"),
        )
        self.prod2 = Product.objects.create(
            name="Add-on Storage",
            sku="SKU-STORAGE",
            unit_price=Decimal("50.00"),
        )
        self.plan = Plan.objects.create(
            name="Monthly Plan",
            billing_interval=Plan.BillingInterval.MONTHLY,
            billing_interval_count=1,
            price=Decimal("150.00"),
        )
        self.sub = Subscription.objects.create(
            subscription_number="SUB-DISC-001",
            customer=self.customer,
            plan=self.plan,
            start_date=self.today - timedelta(days=30),
            next_billing_date=self.today,
            status=Subscription.Status.ACTIVE,
        )
        self.line1 = SubscriptionLine.objects.create(
            subscription=self.sub,
            product=self.prod1,
            quantity=1,
            unit_price=Decimal("100.00"),
            amount=Decimal("100.00"),
        )
        self.line2 = SubscriptionLine.objects.create(
            subscription=self.sub,
            product=self.prod2,
            quantity=2,
            unit_price=Decimal("50.00"),
            amount=Decimal("100.00"),
        )

    def test_discount_validation(self):
        # Value must be > 0
        d_invalid_val = Discount(
            name="Zero Value",
            discount_type=Discount.DiscountType.FIXED,
            value=Decimal("0.00"),
            start_date=self.today,
            end_date=self.today + timedelta(days=10),
        )
        with self.assertRaises(ValidationError):
            d_invalid_val.clean()

        # Percentage cannot exceed 100
        d_invalid_pct = Discount(
            name="Over 100",
            discount_type=Discount.DiscountType.PERCENTAGE,
            value=Decimal("120.00"),
            start_date=self.today,
            end_date=self.today + timedelta(days=10),
        )
        with self.assertRaises(ValidationError):
            d_invalid_pct.clean()

        # End date cannot be before start date
        d_invalid_dates = Discount(
            name="Backwards Dates",
            discount_type=Discount.DiscountType.FIXED,
            value=Decimal("10.00"),
            start_date=self.today,
            end_date=self.today - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            d_invalid_dates.clean()

    def test_percentage_vs_fixed_calculation_and_cap(self):
        # Percentage discount (20% of $200 = $40.00)
        pct_discount = Discount.objects.create(
            name="20% Off",
            discount_type=Discount.DiscountType.PERCENTAGE,
            value=Decimal("20.00"),
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
            applies_to=Discount.AppliesTo.ALL,
        )
        subtotal = Decimal("200.00")
        calc_pct = DiscountService.calculate(pct_discount, subtotal=subtotal)
        self.assertEqual(calc_pct, Decimal("40.00"))

        # Fixed discount ($30 off $200 = $30.00)
        fixed_discount = Discount.objects.create(
            name="$30 Off",
            discount_type=Discount.DiscountType.FIXED,
            value=Decimal("30.00"),
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
            applies_to=Discount.AppliesTo.ALL,
        )
        calc_fixed = DiscountService.calculate(fixed_discount, subtotal=subtotal)
        self.assertEqual(calc_fixed, Decimal("30.00"))

        # Cap verification: Fixed discount ($250 off $200) must cap at $200.00
        big_fixed = Discount.objects.create(
            name="Huge $250 Off",
            discount_type=Discount.DiscountType.FIXED,
            value=Decimal("250.00"),
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
            applies_to=Discount.AppliesTo.ALL,
        )
        calc_capped = DiscountService.calculate(big_fixed, subtotal=subtotal)
        self.assertEqual(calc_capped, Decimal("200.00"))

    def test_product_specific_discount(self):
        prod_discount = Discount.objects.create(
            name="50% Off Add-on Storage Only",
            discount_type=Discount.DiscountType.PERCENTAGE,
            value=Decimal("50.00"),
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
            applies_to=Discount.AppliesTo.PRODUCTS,
        )
        prod_discount.products.add(self.prod2)

        lines = [self.line1, self.line2]  # line1=$100 (prod1), line2=$100 (prod2)
        # Should apply only to line2 ($100), 50% of $100 = $50.00
        calc_prod = DiscountService.calculate(prod_discount, lines=lines)
        self.assertEqual(calc_prod, Decimal("50.00"))

    def test_usage_limit_stops_applying(self):
        limited_discount = Discount.objects.create(
            name="Limited to 2 Uses",
            discount_type=Discount.DiscountType.FIXED,
            value=Decimal("10.00"),
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
            usage_limit=2,
            usage_count=0,
            applies_to=Discount.AppliesTo.ALL,
        )

        inv1 = Invoice.objects.create(
            customer=self.customer,
            subscription=self.sub,
            issue_date=self.today,
            due_date=self.today + timedelta(days=15),
            billing_period_start=self.today,
            billing_period_end=self.today + timedelta(days=30),
            subtotal=Decimal("100.00"),
            total_amount=Decimal("90.00"),
        )
        inv2 = Invoice.objects.create(
            customer=self.customer,
            subscription=self.sub,
            issue_date=self.today,
            due_date=self.today + timedelta(days=15),
            billing_period_start=self.today + timedelta(days=31),
            billing_period_end=self.today + timedelta(days=60),
            subtotal=Decimal("100.00"),
            total_amount=Decimal("90.00"),
        )
        inv3 = Invoice.objects.create(
            customer=self.customer,
            subscription=self.sub,
            issue_date=self.today,
            due_date=self.today + timedelta(days=15),
            billing_period_start=self.today + timedelta(days=61),
            billing_period_end=self.today + timedelta(days=90),
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        )

        # Apply 1st time
        usage1 = DiscountService.apply(limited_discount, inv1, Decimal("10.00"))
        self.assertIsNotNone(usage1)
        limited_discount.refresh_from_db()
        self.assertEqual(limited_discount.usage_count, 1)

        # Apply 2nd time
        usage2 = DiscountService.apply(limited_discount, inv2, Decimal("10.00"))
        self.assertIsNotNone(usage2)
        limited_discount.refresh_from_db()
        self.assertEqual(limited_discount.usage_count, 2)

        # 3rd time: usage limit reached, must not be eligible and apply must raise ValidationError
        eligible = DiscountService.get_eligible_discounts(subtotal=Decimal("100.00"), on_date=self.today)
        self.assertNotIn(limited_discount, eligible)

        with self.assertRaises(ValidationError):
            DiscountService.apply(limited_discount, inv3, Decimal("10.00"))

    def test_date_expiry_stops_applying(self):
        expired_discount = Discount.objects.create(
            name="Past Sale",
            discount_type=Discount.DiscountType.PERCENTAGE,
            value=Decimal("10.00"),
            start_date=self.today - timedelta(days=30),
            end_date=self.today - timedelta(days=1),
            applies_to=Discount.AppliesTo.ALL,
        )
        future_discount = Discount.objects.create(
            name="Upcoming Black Friday",
            discount_type=Discount.DiscountType.PERCENTAGE,
            value=Decimal("10.00"),
            start_date=self.today + timedelta(days=10),
            end_date=self.today + timedelta(days=20),
            applies_to=Discount.AppliesTo.ALL,
        )

        eligible = DiscountService.get_eligible_discounts(subtotal=Decimal("100.00"), on_date=self.today)
        self.assertNotIn(expired_discount, eligible)
        self.assertNotIn(future_discount, eligible)

    def test_duplicate_discount_on_same_invoice_prohibited(self):
        discount = Discount.objects.create(
            name="Promo 10",
            discount_type=Discount.DiscountType.FIXED,
            value=Decimal("10.00"),
            start_date=self.today,
            end_date=self.today + timedelta(days=10),
            applies_to=Discount.AppliesTo.ALL,
        )
        inv = Invoice.objects.create(
            customer=self.customer,
            subscription=self.sub,
            issue_date=self.today,
            due_date=self.today + timedelta(days=15),
            billing_period_start=self.today,
            billing_period_end=self.today + timedelta(days=30),
            subtotal=Decimal("100.00"),
            total_amount=Decimal("90.00"),
        )
        DiscountService.apply(discount, inv, Decimal("10.00"))

        # Re-applying to same invoice must fail
        with self.assertRaises(ValidationError):
            DiscountService.apply(discount, inv, Decimal("10.00"))

