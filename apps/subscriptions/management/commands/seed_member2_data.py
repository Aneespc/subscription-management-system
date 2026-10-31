from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.accounts.models import User, CustomerProfile
from apps.products.models import Product, ProductVariant
from apps.plans.models import Plan
from apps.quotations.models import Quotation, QuotationLine, QuotationTemplate, QuotationTemplateLine
from apps.quotations.services import QuotationService
from apps.subscriptions.models import Subscription, SubscriptionLine
from apps.subscriptions.services import SubscriptionService


class Command(BaseCommand):
    help = "Seed database with Brightloop products, variants (Odoo +$560), plans, templates, quotes, and subscriptions."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding Brightloop initial data for Member 2..."))

        # 1. Users
        admin_user, _ = User.objects.get_or_create(
            username="admin",
            email="admin@brightloop.com",
            defaults={"first_name": "Brightloop", "last_name": "Admin", "role": User.Role.ADMIN, "is_staff": True, "is_superuser": True}
        )
        admin_user.set_password("Admin@123!")
        admin_user.save()

        sales_user, _ = User.objects.get_or_create(
            username="alex_sales",
            email="alex@brightloop.com",
            defaults={"first_name": "Alex", "last_name": "Vance", "role": User.Role.STAFF, "is_staff": True}
        )
        sales_user.set_password("Staff@123!")
        sales_user.save()

        # Customer 1
        c1_user, _ = User.objects.get_or_create(
            username="apex_user",
            email="ops@apexindustries.com",
            defaults={"first_name": "Sarah", "last_name": "Connor", "role": User.Role.CUSTOMER}
        )
        c1_user.set_password("Customer@123!")
        c1_user.save()
        c1_profile, _ = CustomerProfile.objects.get_or_create(
            user=c1_user,
            defaults={
                "company_name": "Apex Industries Inc.",
                "phone": "+1 (555) 234-5678",
                "address": "450 Industrial Parkway, Chicago, IL",
                "tax_number": "US-TAX-8921"
            }
        )

        # Customer 2
        c2_user, _ = User.objects.get_or_create(
            username="brightcraft_user",
            email="hello@brightcraft.io",
            defaults={"first_name": "Leo", "last_name": "Martin", "role": User.Role.CUSTOMER}
        )
        c2_user.set_password("Customer@123!")
        c2_user.save()
        c2_profile, _ = CustomerProfile.objects.get_or_create(
            user=c2_user,
            defaults={
                "company_name": "Brightcraft Studios",
                "phone": "+1 (555) 987-6543",
                "address": "78 Creative Alley, Austin, TX",
                "tax_number": "US-TAX-4412"
            }
        )

        # Customer 3
        c3_user, _ = User.objects.get_or_create(
            username="stellar_user",
            email="billing@stellarlogistics.com",
            defaults={"first_name": "Marcus", "last_name": "Brody", "role": User.Role.CUSTOMER}
        )
        c3_user.set_password("Customer@123!")
        c3_user.save()
        c3_profile, _ = CustomerProfile.objects.get_or_create(
            user=c3_user,
            defaults={
                "company_name": "Stellar Logistics LLC",
                "phone": "+1 (555) 345-6789",
                "address": "900 Harbor Blvd, Seattle, WA",
                "tax_number": "US-TAX-7729"
            }
        )

        # 2. Products and Variants (including Odoo brand +$560)
        p_erp, _ = Product.objects.get_or_create(
            name="Brightloop Business ERP",
            defaults={
                "product_type": "SOFTWARE",
                "sales_price": Decimal("1200.00"),
                "cost_price": Decimal("400.00"),
                "notes": "Core ERP software with inventory, accounting, and sales operations."
            }
        )
        var_standard, _ = ProductVariant.objects.get_or_create(
            product=p_erp,
            attribute_name="Brand Edition",
            attribute_value="Standard Edition",
            defaults={"price_extra": Decimal("0.00")}
        )
        # As per the PDF prompt: "choosing the Odoo brand adds 560 to the price"
        var_odoo, _ = ProductVariant.objects.get_or_create(
            product=p_erp,
            attribute_name="Brand Edition",
            attribute_value="Odoo Brand Edition",
            defaults={"price_extra": Decimal("560.00")}
        )

        p_analytics, _ = Product.objects.get_or_create(
            name="Analytics & Revenue Insights Pro",
            defaults={
                "product_type": "SOFTWARE",
                "sales_price": Decimal("450.00"),
                "cost_price": Decimal("100.00"),
                "notes": "Real-time subscription cohort analytics, MRR, churn forecasting."
            }
        )

        p_support, _ = Product.objects.get_or_create(
            name="24/7 Dedicated Support Add-on",
            defaults={
                "product_type": "SERVICE",
                "sales_price": Decimal("250.00"),
                "cost_price": Decimal("80.00"),
                "notes": "1-hour SLA response with dedicated technical account manager."
            }
        )

        p_connector, _ = Product.objects.get_or_create(
            name="Custom API & Webhook Connector",
            defaults={
                "product_type": "ADDON",
                "sales_price": Decimal("300.00"),
                "cost_price": Decimal("50.00"),
                "notes": "High-throughput API gateway with bi-directional syncing."
            }
        )

        # 3. Plans
        plan_monthly, _ = Plan.objects.get_or_create(
            name="Business Monthly Plan",
            defaults={
                "price": Decimal("180.00"),
                "billing_interval": "MONTHLY",
                "minimum_quantity": 2,
                "allow_pause": True,
                "allow_renewal": True,
                "allow_early_close": True,
                "auto_close": False,
            }
        )

        plan_yearly, _ = Plan.objects.get_or_create(
            name="Enterprise Annual Contract",
            defaults={
                "price": Decimal("1800.00"),
                "billing_interval": "YEARLY",
                "minimum_quantity": 5,
                "allow_pause": False,
                "allow_renewal": True,
                "allow_early_close": False,
                "auto_close": False,
            }
        )

        plan_trial, _ = Plan.objects.get_or_create(
            name="Weekly Fast-Track Trial",
            defaults={
                "price": Decimal("49.00"),
                "billing_interval": "WEEKLY",
                "minimum_quantity": 1,
                "allow_pause": True,
                "allow_renewal": False,
                "allow_early_close": True,
                "auto_close": True,  # Closes on its own when it ends!
            }
        )

        # 4. Quotation Templates
        t_erp, _ = QuotationTemplate.objects.get_or_create(
            name="Standard Cloud ERP Bundle",
            defaults={
                "plan": plan_monthly,
                "validity_days": 30,
                "created_by": sales_user,
                "description": "Standard business configuration with core ERP and support.",
                "is_active": True
            }
        )
        QuotationTemplateLine.objects.get_or_create(
            template=t_erp,
            product=p_erp,
            defaults={"variant": var_standard, "quantity": 2}
        )
        QuotationTemplateLine.objects.get_or_create(
            template=t_erp,
            product=p_support,
            defaults={"quantity": 1}
        )

        t_odoo, _ = QuotationTemplate.objects.get_or_create(
            name="Odoo Enterprise Premium Package",
            defaults={
                "plan": plan_yearly,
                "validity_days": 45,
                "created_by": sales_user,
                "description": "Complete suite with Odoo Brand edition (+$560), Analytics, and API Connector.",
                "is_active": True
            }
        )
        QuotationTemplateLine.objects.get_or_create(
            template=t_odoo,
            product=p_erp,
            defaults={"variant": var_odoo, "quantity": 5}
        )
        QuotationTemplateLine.objects.get_or_create(
            template=t_odoo,
            product=p_analytics,
            defaults={"quantity": 1}
        )
        QuotationTemplateLine.objects.get_or_create(
            template=t_odoo,
            product=p_connector,
            defaults={"quantity": 1}
        )

        # 5. Quotations
        today = timezone.now().date()

        q1, _ = Quotation.objects.get_or_create(
            quotation_number="QT-2026-0001",
            defaults={
                "customer": c1_profile,
                "template": t_erp,
                "created_by": sales_user,
                "issue_date": today,
                "expiry_date": today + timedelta(days=30),
                "payment_terms": Quotation.PaymentTerms.NET_30,
                "status": Quotation.Status.QUOTATION,
                "notes": "Offer prepared for Apex Industries expansion."
            }
        )
        if not q1.lines.exists():
            QuotationLine.objects.create(quotation=q1, product=p_erp, variant=var_standard, quantity=3, unit_price=Decimal("1200.00"), tax_rate=Decimal("10.00"))
            QuotationLine.objects.create(quotation=q1, product=p_support, quantity=1, unit_price=Decimal("250.00"), tax_rate=Decimal("10.00"))
            QuotationService.recalculate_totals(q1)

        q2, _ = Quotation.objects.get_or_create(
            quotation_number="QT-2026-0002",
            defaults={
                "customer": c2_profile,
                "template": t_odoo,
                "created_by": sales_user,
                "issue_date": today - timedelta(days=5),
                "expiry_date": today + timedelta(days=40),
                "payment_terms": Quotation.PaymentTerms.NET_15,
                "status": Quotation.Status.CONFIRMED,
                "notes": "Includes Odoo brand surcharge (+$560 per seat) for 5 seats."
            }
        )
        if not q2.lines.exists():
            QuotationLine.objects.create(quotation=q2, product=p_erp, variant=var_odoo, quantity=5, unit_price=Decimal("1760.00"), tax_rate=Decimal("10.00"))
            QuotationLine.objects.create(quotation=q2, product=p_analytics, quantity=1, unit_price=Decimal("450.00"), tax_rate=Decimal("10.00"))
            QuotationService.recalculate_totals(q2)

        # 6. Subscriptions
        sub_service = SubscriptionService()

        sub1, _ = Subscription.objects.get_or_create(
            subscription_number="SUB-2026-0001",
            defaults={
                "customer": c1_profile,
                "plan": plan_monthly,
                "start_date": today - timedelta(days=15),
                "expiry_date": today + timedelta(days=350),
                "next_billing_date": today + timedelta(days=15),
                "payment_terms": Subscription.PaymentTerms.NET_30,
                "status": Subscription.Status.ACTIVE
            }
        )
        if not sub1.lines.exists():
            SubscriptionLine.objects.create(subscription=sub1, product=p_erp, variant=var_standard, quantity=3, unit_price=Decimal("1200.00"), tax_rate=Decimal("10.00"), amount=Decimal("3600.00"))
            SubscriptionLine.objects.create(subscription=sub1, product=p_support, quantity=1, unit_price=Decimal("250.00"), tax_rate=Decimal("10.00"), amount=Decimal("250.00"))

        sub2, _ = Subscription.objects.get_or_create(
            subscription_number="SUB-2026-0002",
            defaults={
                "customer": c2_profile,
                "plan": plan_yearly,
                "quotation": q2,
                "start_date": today - timedelta(days=10),
                "expiry_date": today + timedelta(days=355),
                "next_billing_date": today + timedelta(days=355),
                "payment_terms": Subscription.PaymentTerms.NET_15,
                "status": Subscription.Status.ACTIVE
            }
        )
        if not sub2.lines.exists():
            SubscriptionLine.objects.create(subscription=sub2, product=p_erp, variant=var_odoo, quantity=5, unit_price=Decimal("1760.00"), tax_rate=Decimal("10.00"), amount=Decimal("8800.00"))
            SubscriptionLine.objects.create(subscription=sub2, product=p_analytics, quantity=1, unit_price=Decimal("450.00"), tax_rate=Decimal("10.00"), amount=Decimal("450.00"))

        sub3, _ = Subscription.objects.get_or_create(
            subscription_number="SUB-2026-0003",
            defaults={
                "customer": c3_profile,
                "plan": plan_monthly,
                "start_date": today - timedelta(days=60),
                "expiry_date": today + timedelta(days=300),
                "next_billing_date": None,
                "payment_terms": Subscription.PaymentTerms.NET_30,
                "status": Subscription.Status.PAUSED
            }
        )
        if not sub3.lines.exists():
            SubscriptionLine.objects.create(subscription=sub3, product=p_erp, variant=var_standard, quantity=2, unit_price=Decimal("1200.00"), tax_rate=Decimal("10.00"), amount=Decimal("2400.00"))

        sub4, _ = Subscription.objects.get_or_create(
            subscription_number="SUB-2026-0004",
            defaults={
                "customer": c3_profile,
                "plan": plan_trial,
                "start_date": today,
                "expiry_date": today + timedelta(days=7),
                "next_billing_date": today + timedelta(days=7),
                "payment_terms": Subscription.PaymentTerms.IMMEDIATE,
                "status": Subscription.Status.CONFIRMED
            }
        )
        if not sub4.lines.exists():
            SubscriptionLine.objects.create(subscription=sub4, product=p_connector, quantity=1, unit_price=Decimal("300.00"), tax_rate=Decimal("10.00"), amount=Decimal("300.00"))

        self.stdout.write(self.style.SUCCESS("Database seeded successfully with Member 2 data!"))
