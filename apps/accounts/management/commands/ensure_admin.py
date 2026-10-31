import os

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.accounts.validators import PasswordComplexityValidator


class Command(BaseCommand):
    help = "Create or update the admin account from the ADMIN_USER and ADMIN_PASS environment variables."

    def handle(self, *args, **options):
        email = os.environ.get("ADMIN_USER", "").strip().lower()
        password = os.environ.get("ADMIN_PASS", "")
        if not email or not password:
            self.stdout.write(self.style.WARNING("ADMIN_USER or ADMIN_PASS not set, skipping admin bootstrap."))
            return
        if "@" not in email:
            raise CommandError("ADMIN_USER must be an email address.")
        try:
            PasswordComplexityValidator().validate(password)
        except ValidationError as exc:
            raise CommandError(f"ADMIN_PASS is too weak: {' '.join(exc.messages)}")

        user, created = User.objects.get_or_create(
            email=email, defaults={"username": email, "role": User.Role.ADMIN, "is_staff": True, "is_superuser": True}
        )
        user.role = User.Role.ADMIN
        user.is_active = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Admin account {'created' if created else 'updated'}: {email}"))
