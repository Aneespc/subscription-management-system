import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Block until the database accepts connections."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=60)

    def handle(self, *args, **options):
        deadline = time.time() + options["timeout"]
        while True:
            try:
                connections["default"].cursor()
                self.stdout.write(self.style.SUCCESS("Database is ready."))
                return
            except OperationalError:
                if time.time() > deadline:
                    raise CommandError("Database did not become available in time.")
                self.stdout.write("Waiting for database...")
                time.sleep(2)
