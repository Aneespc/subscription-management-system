from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from .forms import LoginForm, ProfileForm, RegisterForm, StaffForm
from .mixins import AdminRequiredMixin
from .models import CustomerProfile, User


def customer_landing(user):
    from apps.subscriptions.models import Subscription

    if Subscription.objects.filter(customer__user=user).exists():
        return "subscriptions:list"
    return "subscriptions:plans"


class HomeView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if request.user.is_staff_role:
            return redirect("dashboard:index")
        return redirect(customer_landing(request.user))


class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("subscriptions:plans")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, "Welcome to Brightloop. Your account is ready.")
        return response


class UserLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return reverse("home")


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("accounts:login")


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None):
        profile, _ = CustomerProfile.objects.get_or_create(
            user=self.request.user, defaults={"company_name": self.request.user.email}
        )
        return profile

    def form_valid(self, form):
        messages.success(self.request, "Profile updated.")
        return super().form_valid(form)


class UserPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["email"].widget.attrs.update({"class": "form-control", "placeholder": "you@company.com"})
        return form


class UserPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class UserPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for field in form.fields.values():
            field.widget.attrs.update({"class": "form-control"})
        return form


class UserPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


class StaffListView(AdminRequiredMixin, ListView):
    template_name = "staff/staff_list.html"
    context_object_name = "members"

    def get_queryset(self):
        return User.objects.filter(role__in=[User.Role.ADMIN, User.Role.STAFF]).order_by("role", "email")


class StaffCreateView(AdminRequiredMixin, CreateView):
    form_class = StaffForm
    template_name = "staff/staff_form.html"
    success_url = reverse_lazy("accounts:staff_list")

    def form_valid(self, form):
        messages.success(self.request, f"Team member {form.cleaned_data['email']} added.")
        return super().form_valid(form)
