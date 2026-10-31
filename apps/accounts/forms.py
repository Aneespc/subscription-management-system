from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import CustomerProfile, User

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Email",
        widget=forms.EmailInput({**TEXT, "autofocus": True, "placeholder": "you@company.com"}),
    )
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(TEXT))

    def clean_username(self):
        return self.cleaned_data["username"].lower()


class RegisterForm(UserCreationForm):
    email = forms.EmailField(widget=forms.EmailInput({**TEXT, "placeholder": "you@company.com"}))

    class Meta:
        model = User
        fields = ["email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update(TEXT)
        self.fields["password2"].widget.attrs.update(TEXT)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = user.email
        user.role = User.Role.CUSTOMER
        if commit:
            user.save()
            CustomerProfile.objects.create(user=user, company_name=user.email.split("@")[0], billing_email=user.email)
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomerProfile
        fields = ["company_name", "phone", "address", "tax_number", "billing_email"]
        widgets = {
            "company_name": forms.TextInput(TEXT),
            "phone": forms.TextInput(TEXT),
            "address": forms.Textarea({**TEXT, "rows": 3}),
            "tax_number": forms.TextInput(TEXT),
            "billing_email": forms.EmailInput(TEXT),
        }


class StaffForm(UserCreationForm):
    email = forms.EmailField(widget=forms.EmailInput(TEXT))
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(TEXT))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(TEXT))
    role = forms.ChoiceField(
        choices=[(User.Role.STAFF, "Staff"), (User.Role.ADMIN, "Admin")],
        initial=User.Role.STAFF,
        widget=forms.Select(SELECT),
    )

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "role"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update(TEXT)
        self.fields["password2"].widget.attrs.update(TEXT)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = user.email
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
        return user
