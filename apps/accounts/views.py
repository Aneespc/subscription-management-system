from django.shortcuts import redirect, render
from django.contrib.auth import login, logout
from django.contrib import messages
from .models import User


def switch_user(request, username):
    """Utility view for demo & testing: switch between Customer, Staff, Admin, or Guest."""
    if username == "logout":
        logout(request)
        messages.info(request, "Logged out. You are now viewing as Guest.")
        return redirect("subscriptions:list")

    try:
        user = User.objects.get(username=username)
        login(request, user)
        role_label = user.get_role_display()
        name = user.customer_profile.company_name if hasattr(user, "customer_profile") and user.customer_profile else user.get_full_name() or user.username
        messages.success(request, f"Switched persona to: {name} ({role_label})")
    except User.DoesNotExist:
        messages.error(request, f"User {username} not found.")

    return redirect("subscriptions:list")
