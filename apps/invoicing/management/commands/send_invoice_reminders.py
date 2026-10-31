from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.invoicing.services import InvoiceService


class Command(BaseCommand):
    help = "Email unsent confirmed invoices, remind customers before the due date, and chase overdue invoices."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default=None, help="Run date (YYYY-MM-DD), defaults to today.")
        parser.add_argument("--days-before", type=int, default=None)
        parser.add_argument("--repeat-every", type=int, default=None)

    def handle(self, *args, **options):
        today = None
        if options["date"]:
            try:
                today = datetime.strptime(options["date"], "%Y-%m-%d").date()
            except ValueError:
                raise CommandError(f"Invalid date '{options['date']}'. Expected YYYY-MM-DD.")
        result = InvoiceService.send_due_notifications(
            today=today, days_before=options["days_before"], repeat_days=options["repeat_every"]
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Emails sent: {result['invoice']} invoice(s), {result['due']} due reminder(s), "
                f"{result['overdue']} overdue reminder(s). Failed: {len(result['failed'])}."
            )
        )
        for item in result["failed"]:
            self.stdout.write(self.style.ERROR(f"  ! {item['invoice']} ({item['kind']}): {item['error']}"))
