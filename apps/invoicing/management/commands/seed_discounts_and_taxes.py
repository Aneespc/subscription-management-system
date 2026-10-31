from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import CustomerProfile, User
from apps.discounts.models import Discount
from apps.invoicing.models import Tax
from apps.plans.models import Plan
from apps.products.models import Product
from apps.subscriptions.models import Subscription, SubscriptionLine


class Command(BaseCommand):
    help = "Seed sample taxes, discounts, and optional sample test data."

    def handle(self, *args, **options):
        today = timezone.now().date()

        self.stdout.write("Seeding sample Taxes...")
        taxes = [
            ("Standard GST", Decimal("18.00"), "Standard 18% Goods & Services Tax", True),
            ("Standard VAT", Decimal("20.00"), "European Union Standard VAT", True),
            ("Reduced VAT", Decimal("5.00"), "Reduced 5% Value Added Tax", True),
            ("State Sales Tax", Decimal("8.50"), "United States Average State Sales Tax", True),
            ("Zero Rate Tax", Decimal("0.00"), "Exempt or 0% Export Tax Rate", True),
            ("Legacy Tax", Decimal("12.50"), "Deprecated legacy rate", False),
        ]
        created_taxes = 0
        for name, rate, desc, active in taxes:
            obj, created = Tax.objects.get_or_create(
                name=name,
                defaults={"rate": rate, "description": desc, "is_active": active},
            )
            if created:
                created_taxes += 1
        self.stdout.write(self.style.SUCCESS(f"Taxes seeded ({created_taxes} newly created)."))

        self.stdout.write("Seeding sample Discounts...")
        discounts = [
            {
                "name": "Welcome New Customer (20%)",
                "discount_type": Discount.DiscountType.PERCENTAGE,
                "value": Decimal("20.00"),
                "minimum_purchase": Decimal("30.00"),
                "minimum_quantity": 1,
                "start_date": today - timedelta(days=30),
                "end_date": today + timedelta(days=335),
                "usage_limit": 500,
                "applies_to": Discount.AppliesTo.ALL,
                "is_active": True,
            },
            {
                "name": "Fixed $15 Off Recurring Billing",
                "discount_type": Discount.DiscountType.FIXED,
                "value": Decimal("15.00"),
                "minimum_purchase": Decimal("40.00"),
                "minimum_quantity": None,
                "start_date": today - timedelta(days=10),
                "end_date": today + timedelta(days=180),
                "usage_limit": 100,
                "applies_to": Discount.AppliesTo.SUBSCRIPTIONS,
                "is_active": True,
            },
            {
                "name": "Annual Saver (10%)",
                "discount_type": Discount.DiscountType.PERCENTAGE,
                "value": Decimal("10.00"),
                "minimum_purchase": Decimal("100.00"),
                "minimum_quantity": None,
                "start_date": today - timedelta(days=60),
                "end_date": today + timedelta(days=305),
                "usage_limit": None,
                "applies_to": Discount.AppliesTo.ALL,
                "is_active": True,
            },
            {
                "name": "Expired Flash Sale (30%)",
                "discount_type": Discount.DiscountType.PERCENTAGE,
                "value": Decimal("30.00"),
                "minimum_purchase": None,
                "minimum_quantity": None,
                "start_date": today - timedelta(days=90),
                "end_date": today - timedelta(days=10),
                "usage_limit": 50,
                "applies_to": Discount.AppliesTo.ALL,
                "is_active": True,
            },
            {
                "name": "Maxed Out Quota Discount ($25)",
                "discount_type": Discount.DiscountType.FIXED,
                "value": Decimal("25.00"),
                "minimum_purchase": None,
                "minimum_quantity": None,
                "start_date": today - timedelta(days=15),
                "end_date": today + timedelta(days=15),
                "usage_limit": 5,
                "usage_count": 5,
                "applies_to": Discount.AppliesTo.ALL,
                "is_active": True,
            },
        ]
        created_discounts = 0
        for d_data in discounts:
            obj, created = Discount.objects.get_or_create(
                name=d_data["name"],
                defaults=d_data,
            )
            if created:
                created_discounts += 1
        self.stdout.write(self.style.SUCCESS(f"Discounts seeded ({created_discounts} newly created)."))

        # Seed sample demo accounts and subscriptions if none exist
        if not User.objects.filter(username="admin").exists():
            admin_user = User.objects.create_superuser(
                username="admin",
                email="admin@brightloopsoftware.com",
                password="adminpassword123",
                role=User.Role.ADMIN,
            )
            self.stdout.write("Created default admin user: admin / adminpassword123")

        if not User.objects.filter(username="staff1").exists():
            staff_user = User.objects.create_user(
                username="staff1",
                email="staff@brightloopsoftware.com",
                password="staffpassword123",
                role=User.Role.STAFF,
            )
            self.stdout.write("Created staff user: staff1 / staffpassword123")

        if not CustomerProfile.objects.exists():
            cust_user = User.objects.create_user(
                username="acme_corp",
                email="billing@acmecorp.com",
                password="customerpass123",
                role=User.Role.CUSTOMER,
            )
            cust_profile = CustomerProfile.objects.create(
                user=cust_user,
                company_name="Acme Corporation",
                billing_email="billing@acmecorp.com",
                billing_address="100 Innovation Way, Suite 400, San Francisco, CA 94105",
                tax_id="US-94-1234567",
            )

            # Create products
            p1, _ = Product.objects.get_or_create(
                sku="PROD-CLOUD-CORE",
                defaults={"name": "Brightloop Cloud Core", "unit_price": Decimal("99.00"), "description": "Cloud Core Engine"},
            )
            p2, _ = Product.objects.get_or_create(
                sku="PROD-API-PACK",
                defaults={"name": "API Enterprise Pack", "unit_price": Decimal("49.00"), "description": "High Throughput API"},
            )

            # Create plan
            plan, _ = Plan.objects.get_or_create(
                name="Pro SaaS Monthly",
                defaults={
                    "billing_interval": Plan.BillingInterval.MONTHLY,
                    "billing_interval_count": 1,
                    "price": Decimal("148.00"),
                },
            )

            # Create subscription
            sub = Subscription.objects.create(
                subscription_number="SUB-2026-0001",
                customer=cust_profile,
                plan=plan,
                start_date=today - timedelta(days=30),
                next_billing_date=today,
                payment_terms=15,
                status=Subscription.Status.ACTIVE,
            )
            SubscriptionLine.objects.create(
                subscription=sub,
                product=p1,
                quantity=1,
                unit_price=Decimal("99.00"),
                tax_rate=Decimal("18.00"),
                amount=Decimal("99.00"),
            )
            SubscriptionLine.objects.create(
                subscription=sub,
                product=p2,
                quantity=2,
                unit_price=Decimal("49.00"),
                tax_rate=Decimal("18.00"),
                amount=Decimal("98.00"),
            )
            self.stdout.write("Created sample Customer, Products, Plan, and Active Subscription due today.")

