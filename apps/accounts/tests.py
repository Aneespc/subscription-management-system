from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import CustomerProfile, User
from .validators import PasswordComplexityValidator


class PasswordRuleTests(TestCase):
    def test_rejects_weak_passwords(self):
        validator = PasswordComplexityValidator()
        for weak in ["short1!A", "alllowercase1!", "ALLUPPERCASE1!", "NoSpecial123"]:
            with self.assertRaises(ValidationError):
                validator.validate(weak)

    def test_accepts_strong_password(self):
        PasswordComplexityValidator().validate("Str0ng!Pass")


class RegistrationTests(TestCase):
    def payload(self, **overrides):
        data = {"email": "owner@shop.com", "password1": "Str0ng!Pass", "password2": "Str0ng!Pass"}
        data.update(overrides)
        return data

    def test_register_creates_customer_and_profile(self):
        response = self.client.post(reverse("accounts:register"), self.payload())
        self.assertRedirects(response, reverse("subscriptions:plans"))
        user = User.objects.get(email="owner@shop.com")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(CustomerProfile.objects.filter(user=user).exists())

    def test_duplicate_email_rejected(self):
        self.client.post(reverse("accounts:register"), self.payload())
        self.client.logout()
        response = self.client.post(reverse("accounts:register"), self.payload(email="Owner@Shop.com"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email="owner@shop.com").count(), 1)

    def test_weak_password_rejected(self):
        response = self.client.post(reverse("accounts:register"), self.payload(password1="weakpass", password2="weakpass"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="owner@shop.com").exists())

    def test_login_with_email(self):
        self.client.post(reverse("accounts:register"), self.payload())
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"username": "Owner@Shop.com", "password": "Str0ng!Pass"})
        self.assertEqual(response.status_code, 302)

    def test_superuser_created_with_plain_username_can_login_by_email(self):
        User.objects.create_superuser(username="boss", email="Boss@Example.com", password="Str0ng!Pass")
        response = self.client.post(reverse("accounts:login"), {"username": "boss@example.com", "password": "Str0ng!Pass"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(username="boss").role, User.Role.ADMIN)

    def test_password_reset_sends_link(self):
        from django.core import mail

        self.client.post(reverse("accounts:register"), self.payload())
        self.client.logout()
        self.client.post(reverse("accounts:password_reset"), {"email": "owner@shop.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)


class RoleAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin@x.com", email="admin@x.com", password="Str0ng!Pass", role=User.Role.ADMIN)
        self.staff = User.objects.create_user(username="staff@x.com", email="staff@x.com", password="Str0ng!Pass", role=User.Role.STAFF)
        self.customer = User.objects.create_user(username="cust@x.com", email="cust@x.com", password="Str0ng!Pass", role=User.Role.CUSTOMER)
        CustomerProfile.objects.create(user=self.customer, company_name="Cust Co")

    def test_only_admin_can_add_staff(self):
        data = {"email": "new@x.com", "first_name": "New", "last_name": "Staff", "role": "STAFF", "password1": "Str0ng!Pass", "password2": "Str0ng!Pass"}
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse("accounts:staff_create"), data).status_code, 403)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(reverse("accounts:staff_create"), data).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse("accounts:staff_create"), data).status_code, 302)
        self.assertEqual(User.objects.get(email="new@x.com").role, "STAFF")

    def test_home_routes_by_role(self):
        from apps.plans.models import Plan
        from apps.subscriptions.models import Subscription

        self.client.force_login(self.customer)
        self.assertRedirects(self.client.get(reverse("home")), reverse("subscriptions:plans"))
        Subscription.objects.create(customer=self.customer.customer_profile, plan=Plan.objects.create(name="P"))
        self.assertRedirects(self.client.get(reverse("home")), reverse("subscriptions:list"))
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse("home")), reverse("dashboard:index"))

    def test_customer_cannot_open_staff_pages(self):
        self.client.force_login(self.customer)
        for name in ["dashboard:index", "products:list", "plans:list", "quotations:list", "payments:list", "accounts:staff_list"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
