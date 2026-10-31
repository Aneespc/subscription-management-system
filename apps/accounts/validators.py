import re

from django.core.exceptions import ValidationError


class PasswordComplexityValidator:
    rules = (
        (lambda p: len(p) > 8, "more than 8 characters"),
        (lambda p: re.search(r"[A-Z]", p), "an uppercase letter"),
        (lambda p: re.search(r"[a-z]", p), "a lowercase letter"),
        (lambda p: re.search(r"[^A-Za-z0-9]", p), "a special character"),
    )

    def validate(self, password, user=None):
        missing = [label for check, label in self.rules if not check(password)]
        if missing:
            raise ValidationError(
                "Password must contain " + ", ".join(missing) + ".",
                code="password_complexity",
            )

    def get_help_text(self):
        return "Your password must be more than 8 characters and include an uppercase letter, a lowercase letter and a special character."
