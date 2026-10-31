from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, CustomerProfile


class RegisterForm(UserCreationForm):

    email = forms.EmailField()
    company_name = forms.CharField(max_length=200)
    phone = forms.CharField(max_length=20, required=False)
    address = forms.CharField(
        widget=forms.Textarea,
        required=False
    )
    tax_number = forms.CharField(
        max_length=50,
        required=False
    )

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email'
        ]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = User.Role.CUSTOMER

        if commit:
            user.save()

            CustomerProfile.objects.create(
                user=user,
                company_name=self.cleaned_data['company_name'],
                phone=self.cleaned_data['phone'],
                address=self.cleaned_data['address'],
                tax_number=self.cleaned_data['tax_number']
            )

        return user


class ProfileForm(forms.ModelForm):

    class Meta:
        model = CustomerProfile
        fields = [
            'company_name',
            'phone',
            'address',
            'tax_number'
        ]