from decimal import Decimal
from django import forms

from apps.accounts.models import CustomerProfile
from apps.invoicing.models import Invoice, Tax
from apps.subscriptions.models import Subscription


class TaxForm(forms.ModelForm):
    class Meta:
        model = Tax
        fields = ["name", "rate", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Standard VAT"}),
            "rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "e.g. 18.00"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional description"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_rate(self):
        rate = self.cleaned_data.get("rate")
        if rate is not None and rate < Decimal("0.00"):
            raise forms.ValidationError("Tax rate cannot be negative.")
        return rate


class InvoiceGenerateForm(forms.Form):
    subscription = forms.ModelChoiceField(
        queryset=Subscription.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select an active subscription to bill.",
    )
    billing_period_start = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        help_text="Start date of the billing period.",
    )
    billing_period_end = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        help_text="End date of the billing period.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subscription"].queryset = (
            Subscription.objects.filter(status=Subscription.Status.ACTIVE)
            .select_related("customer", "plan")
            .order_by("subscription_number")
        )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("billing_period_start")
        end = cleaned_data.get("billing_period_end")

        if start and end and end < start:
            self.add_error("billing_period_end", "Billing period end date cannot be earlier than start date.")

        return cleaned_data


class InvoiceFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Search invoice # or customer..."}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses")] + Invoice.Status.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    customer = forms.ModelChoiceField(
        required=False,
        queryset=CustomerProfile.objects.all().order_by("company_name", "user__username"),
        empty_label="All Customers",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    overdue_only = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

