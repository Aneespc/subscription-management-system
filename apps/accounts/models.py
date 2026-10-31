from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

phone_validator = RegexValidator(r"^\+?[0-9 ()-]{6,30}$", "Enter a valid phone number using digits, spaces, +, - or ().")


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        STAFF = "STAFF", "Staff"
        CUSTOMER = "CUSTOMER", "Customer"

    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    class Meta:
        ordering = ["username"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_staff_role(self):
        return self.role in (self.Role.ADMIN, self.Role.STAFF) or self.is_superuser

    @property
    def is_customer_role(self):
        return self.role == self.Role.CUSTOMER and not self.is_superuser

    @property
    def display_name(self):
        if self.is_customer_role:
            profile = getattr(self, "customer_profile", None)
            if profile and profile.company_name:
                return profile.company_name
        return self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        if self.role == self.Role.ADMIN:
            self.is_staff = True
            self.is_superuser = True
        elif self.role == self.Role.STAFF:
            self.is_staff = True
            self.is_superuser = False
        else:
            self.is_staff = False
            self.is_superuser = False
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)


class CustomerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    company_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True, validators=[phone_validator])
    address = models.TextField(blank=True)
    tax_number = models.CharField(max_length=50, blank=True)
    billing_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company_name"]
        indexes = [models.Index(fields=["company_name"])]

    def __str__(self):
        return self.company_name or self.user.username

    @property
    def contact_email(self):
        return self.billing_email or self.user.email
