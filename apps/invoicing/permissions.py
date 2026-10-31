from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class AdminRequiredMixin(UserPassesTestMixin):
    """Requires user to be authenticated and have ADMIN role (or superuser)."""
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        return getattr(user, "is_admin_role", False) or user.is_superuser

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("Administrator privileges are required to access this resource.")
        return super().handle_no_permission()


class StaffOrAdminRequiredMixin(UserPassesTestMixin):
    """Requires user to be authenticated and have ADMIN or STAFF role (or is_staff/is_superuser)."""
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        return getattr(user, "is_staff_role", False) or user.is_staff or user.is_superuser

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("Staff or Administrator privileges are required to access this resource.")
        return super().handle_no_permission()

