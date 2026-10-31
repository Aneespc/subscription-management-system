import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import CustomerProfile
from apps.invoicing.models import Invoice
from apps.payments.models import Payment

METHODS = [value for value, _ in Payment.PaymentMethod.choices]
CENT = Decimal("0.01")
User = get_user_model()


class Command(BaseCommand):
    help = "Create demo customers, invoices and payments (re-running replaces earlier SEED data)."

    def add_arguments(self, parser):
        parser.add_argument("--invoices", type=int, default=5000)
        parser.add_argument("--customers", type=int, default=50)

    @transaction.atomic
    def handle(self, *args, **opts):
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            raise CommandError("Create a superuser first: python manage.py createsuperuser")

        # Delete in dependency order: payments, invoices, then demo users (cascades to profiles)
        Payment.objects.filter(payment_number__startswith="SEED-").delete()
        Invoice.objects.filter(invoice_number__startswith="SEED-").delete()
        User.objects.filter(username__startswith="seed_cust_").delete()

        customers = []
        for i in range(1, opts["customers"] + 1):
            user = User.objects.create_user(
                username=f"seed_cust_{i}", email=f"seed_cust_{i}@example.com",
                password="Passw0rd!x", role="CUSTOMER",
            )
            customers.append(CustomerProfile.objects.create(
                user=user, company_name=f"Demo Company {i}", phone="0000000000", address="Demo address",
            ))

        today = timezone.localdate()
        now = timezone.now()
        statuses = random.choices(
            [Invoice.Status.PAID, Invoice.Status.CONFIRMED, Invoice.Status.DRAFT, Invoice.Status.CANCELLED],
            weights=[50, 40, 5, 5], k=opts["invoices"],
        )

        invoices = []
        for i, status in enumerate(statuses, start=1):
            due = today + timedelta(days=random.randint(-180, 30))
            invoices.append(Invoice(
                invoice_number=f"SEED-INV-{i:06d}",
                customer=random.choice(customers),
                total_amount=Decimal(random.randint(100, 5000)),
                status=status,
                issue_date=due - timedelta(days=14),
                due_date=due,
                billing_period_start=due - timedelta(days=44),
                billing_period_end=due - timedelta(days=14),
            ))
        Invoice.objects.bulk_create(invoices, batch_size=500)
        saved = Invoice.objects.filter(invoice_number__startswith="SEED-")

        payments, counter = [], 0

        def add(invoice, amount):
            nonlocal counter
            counter += 1
            payments.append(Payment(
                payment_number=f"SEED-PAY-{counter:06d}",
                invoice=invoice,
                amount=amount,
                payment_method=random.choice(METHODS),
                payment_date=now - timedelta(days=random.randint(0, 180), seconds=random.randint(0, 86399)),
                transaction_reference=f"REF{random.randint(100000, 999999)}",
                recorded_by=admin,
            ))

        for inv in saved:
            if inv.status == Invoice.Status.PAID:
                if random.random() < 0.7:
                    add(inv, inv.total_amount)
                else:
                    first = (inv.total_amount * Decimal(random.randint(30, 70)) / 100).quantize(CENT)
                    add(inv, first)
                    add(inv, inv.total_amount - first)
            elif inv.status == Invoice.Status.CONFIRMED and random.random() < 0.3:
                partial = (inv.total_amount * Decimal(random.randint(20, 80)) / 100).quantize(CENT)
                add(inv, partial)

        Payment.objects.bulk_create(payments, batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"Created {len(customers)} customers, {len(invoices)} invoices and {len(payments)} payments."
        ))