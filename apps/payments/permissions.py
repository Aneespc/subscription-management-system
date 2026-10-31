from rest_framework.permissions import BasePermission


class IsStaffOrAdmin(BasePermission):
    """Staff/admin only. Swap in the `role` check once Member 1's User model lands."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        role = getattr(user, "role", None)
        if role is not None:
            return role in ("ADMIN", "STAFF")
        return user.is_staff