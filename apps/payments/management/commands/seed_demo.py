import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.payments.models import Invoice, Payment

METHODS = [value for value, _ in Payment.PaymentMethod.choices]
CENT = Decimal("0.01")


class Command(BaseCommand):
    help = "Create demo invoices and payments (re-running replaces earlier SEED- data)."

    def add_arguments(self, parser):
        parser.add_argument("--invoices", type=int, default=5000)

    @transaction.atomic
    def handle(self, *args, **opts):
        user = get_user_model().objects.filter(is_superuser=True).first()
        if not user:
            raise CommandError("Create a superuser first: python manage.py createsuperuser")

        Payment.objects.filter(payment_number__startswith="SEED-").delete()
        Invoice.objects.filter(invoice_number__startswith="SEED-").delete()

        today = timezone.localdate()
        now = timezone.now()
        statuses = random.choices(
            [Invoice.Status.PAID, Invoice.Status.CONFIRMED, Invoice.Status.DRAFT, Invoice.Status.CANCELLED],
            weights=[50, 40, 5, 5], k=opts["invoices"],
        )

        invoices = [
            Invoice(
                invoice_number=f"SEED-INV-{i:06d}",
                total_amount=Decimal(random.randint(100, 5000)),
                status=status,
                due_date=today + timedelta(days=random.randint(-180, 30)),
            )
            for i, status in enumerate(statuses, start=1)
        ]
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
                recorded_by=user,
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
            f"Created {len(invoices)} invoices and {len(payments)} payments."
        ))