from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = ()

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.role in self.allowed_roles

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("You do not have permission to access this page.")
        return super().handle_no_permission()


class StaffRequiredMixin(RoleRequiredMixin):
    allowed_roles = ("ADMIN", "STAFF")


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ("ADMIN",)


StaffOrAdminRequiredMixin = StaffRequiredMixin


def is_staff_user(user):
    return user.is_authenticated and (user.is_superuser or user.role in ("ADMIN", "STAFF"))


def is_admin_user(user):
    return user.is_authenticated and (user.is_superuser or user.role == "ADMIN")
