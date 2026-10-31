from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.invoicing.services import InvoiceService
from apps.subscriptions.models import Subscription


class Command(BaseCommand):
    help = "Generate due recurring subscription invoices up to a specific billing date."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Target billing run date in YYYY-MM-DD format (defaults to current date).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Simulate the billing run without saving invoices or advancing billing dates.",
        )

    def handle(self, *args, **options):
        date_str = options.get("date")
        dry_run = options.get("dry_run", False)

        if date_str:
            try:
                run_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                raise CommandError(f"Invalid date format '{date_str}'. Expected YYYY-MM-DD.")
        else:
            run_date = timezone.now().date()

        self.stdout.write(
            self.style.NOTICE(
                f"{'[DRY RUN] ' if dry_run else ''}Running recurring invoice generation for date: {run_date}"
            )
        )

        if dry_run:
            due_subs = Subscription.objects.filter(
                status=Subscription.Status.ACTIVE,
                next_billing_date__lte=run_date,
            ).select_related("customer", "plan")

            count = due_subs.count()
            self.stdout.write(f"Found {count} subscription(s) due for billing on or before {run_date}.")
            for sub in due_subs:
                self.stdout.write(
                    f" - [WOULD BILL] Sub #{sub.subscription_number} | Customer: {sub.customer} | "
                    f"Plan: {sub.plan.name} | Next billing: {sub.next_billing_date}"
                )
            self.stdout.write(self.style.SUCCESS("Dry run completed. No database changes were made."))
            return

        result = InvoiceService.generate_due_invoices(run_date=run_date)

        self.stdout.write(
            self.style.SUCCESS(
                f"Invoice generation finished successfully:\n"
                f"  Created: {result['created']}\n"
                f"  Skipped: {result['skipped']}\n"
                f"  Failed:  {result['failed']}"
            )
        )

        if result["created"] > 0:
            for inv in result["invoices"][:10]:
                self.stdout.write(f"  + Generated {inv.invoice_number} | Total: ${inv.total_amount}")
            if result["created"] > 10:
                self.stdout.write(f"  ... and {result['created'] - 10} more.")

        if result["failed"] > 0:
            self.stdout.write(self.style.ERROR("\nFailed subscriptions:"))
            for err in result["errors"]:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ! Sub #{err['subscription_number']} (ID {err['subscription_id']}): {err['error']}"
                    )
                )

