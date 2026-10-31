from rest_framework.permissions import BasePermission


class IsStaffOrAdmin(BasePermission):
    """Superusers, admins and staff only. Customers are blocked from these endpoints."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        role = getattr(user, "role", None)
        if role is not None:
            return role in ("ADMIN", "STAFF")
        return user.is_staff