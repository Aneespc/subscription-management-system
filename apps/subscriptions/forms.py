from django import forms
from django.forms import inlineformset_factory
from .models import Subscription, SubscriptionLine
from apps.accounts.models import CustomerProfile
from apps.plans.models import Plan
from apps.products.models import Product, ProductVariant


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = [
            "customer", "plan", "start_date", "expiry_date",
            "payment_terms", "status"
        ]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "plan": forms.Select(attrs={"class": "form-select"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "payment_terms": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }


class SubscriptionLineForm(forms.ModelForm):
    class Meta:
        model = SubscriptionLine
        fields = ["product", "variant", "quantity", "unit_price", "tax_rate"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select product-select"}),
            "variant": forms.Select(attrs={"class": "form-select variant-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control quantity-input", "min": 1}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control price-input", "step": "0.01"}),
            "tax_rate": forms.NumberInput(attrs={"class": "form-control tax-input", "step": "0.01"}),
        }


SubscriptionLineFormSet = inlineformset_factory(
    Subscription,
    SubscriptionLine,
    form=SubscriptionLineForm,
    extra=1,
    can_delete=True
)


class SubscriptionRenewForm(forms.Form):
    additional_days = forms.IntegerField(
        required=False,
        label="Extension Days (Leave blank to use plan interval)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 30, 365"})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional renewal notes"})
    )
