from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import Payment


class PaymentForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    payment_method = forms.ChoiceField(
        choices=Payment.PaymentMethod.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    payment_date = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"],
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def clean_payment_date(self):
        value = self.cleaned_data["payment_date"]
        if value > timezone.now() + timedelta(minutes=5):
            raise forms.ValidationError("Payment date cannot be in the future.")
        return value


class PaymentFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Payment #, invoice #, customer..."}),
    )
    method = forms.ChoiceField(
        required=False,
        choices=[("", "All methods")] + Payment.PaymentMethod.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("date_from") and cleaned.get("date_to") and cleaned["date_to"] < cleaned["date_from"]:
            self.add_error("date_to", "End date must be on or after the start date.")
        return cleaned
