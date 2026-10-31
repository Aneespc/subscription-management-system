from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        STAFF = "STAFF", "Staff"
        CUSTOMER = "CUSTOMER", "Customer"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def is_staff_member(self):
        return self.role in [self.Role.ADMIN, self.Role.STAFF] or self.is_staff

    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"


class CustomerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="customer_profile")
    company_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    tax_number = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.company_name or self.user.get_full_name() or self.user.email
