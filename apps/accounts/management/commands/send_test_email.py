from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email to check the SMTP configuration."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Recipient email address")

    def handle(self, *args, **options):
        self.stdout.write(f"Backend: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT} TLS={settings.EMAIL_USE_TLS}")
        self.stdout.write(f"User: {settings.EMAIL_HOST_USER or '(not set)'} | password: {'set' if settings.EMAIL_HOST_PASSWORD else 'NOT SET'}")
        self.stdout.write(f"From: {settings.DEFAULT_FROM_EMAIL}")
        if "gmail" in settings.EMAIL_HOST and settings.EMAIL_HOST_PASSWORD and (
            len(settings.EMAIL_HOST_PASSWORD) != 16 or not settings.EMAIL_HOST_PASSWORD.isalpha()
        ):
            self.stdout.write(self.style.WARNING(
                "Gmail app passwords are exactly 16 letters. Remove any spaces or hyphens from EMAIL_HOST_PASSWORD; Gmail silently drops the connection on a wrong password."
            ))
        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            self.stdout.write(self.style.WARNING("Console backend is active: EMAIL_HOST_USER and EMAIL_HOST_PASSWORD are not both set, so mail prints here instead of being sent."))
        try:
            send_mail(
                "Brightloop test email",
                "If you can read this, SMTP is configured correctly.",
                settings.DEFAULT_FROM_EMAIL,
                [options["to"]],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(f"Sending failed: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Test email sent to {options['to']}."))
