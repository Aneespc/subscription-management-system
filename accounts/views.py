from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, UpdateView
from django.urls import reverse_lazy
from django.contrib import messages

from .models import CustomerProfile
from .forms import RegisterForm, ProfileForm


class RegisterView(CreateView):

    form_class = RegisterForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('accounts:profile')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class UserLoginView(LoginView):

    template_name = 'accounts/login.html'


class UserLogoutView(LogoutView):

    next_page = reverse_lazy('accounts:login')


class ProfileView(LoginRequiredMixin, UpdateView):

    model = CustomerProfile
    form_class = ProfileForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self):
        profile, _ = CustomerProfile.objects.get_or_create(
            user=self.request.user,
            defaults={
                'company_name': self.request.user.username
            }
        )
        return profile