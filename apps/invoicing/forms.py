from decimal import Decimal
from django import forms

from apps.accounts.models import CustomerProfile
from apps.invoicing.models import Invoice
from apps.products.models import Tax


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

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class InvoiceFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Invoice #, customer, subscription..."}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses")] + Invoice.Status.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    customer = forms.ModelChoiceField(
        required=False,
        queryset=CustomerProfile.objects.order_by("company_name"),
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

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("date_from") and cleaned.get("date_to") and cleaned["date_to"] < cleaned["date_from"]:
            self.add_error("date_to", "End date must be on or after the start date.")
        return cleaned

