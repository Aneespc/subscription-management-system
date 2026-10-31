from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.invoicing.services import InvoiceService
from apps.subscriptions.models import Subscription


class Command(BaseCommand):
    help = "Generate invoices for every active subscription whose billing date has arrived."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default=None, help="Run date (YYYY-MM-DD), defaults to today.")
        parser.add_argument("--dry-run", action="store_true", default=False)

    def handle(self, *args, **options):
        if options["date"]:
            try:
                run_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
            except ValueError:
                raise CommandError(f"Invalid date '{options['date']}'. Expected YYYY-MM-DD.")
        else:
            run_date = timezone.localdate()

        if options["dry_run"]:
            due = Subscription.objects.filter(
                status=Subscription.Status.ACTIVE, next_billing_date__lte=run_date
            ).select_related("customer", "plan")
            self.stdout.write(f"[DRY RUN] {due.count()} subscription(s) due on or before {run_date}.")
            for sub in due:
                self.stdout.write(f"  - {sub.subscription_number} | {sub.customer} | {sub.plan.name} | due {sub.next_billing_date}")
            return

        result = InvoiceService.generate_due_invoices(run_date=run_date)
        self.stdout.write(
            self.style.SUCCESS(
                f"Billing run for {run_date}: created {result['created']}, skipped {result['skipped']}, "
                f"failed {result['failed']}, auto-closed {result['auto_closed']}."
            )
        )
        for inv in result["invoices"][:20]:
            self.stdout.write(f"  + {inv.invoice_number} | {inv.customer} | total {inv.total_amount}")
        for err in result["errors"]:
            self.stdout.write(self.style.ERROR(f"  ! {err['subscription_number']}: {err['error']}"))
