from django import forms

from .models import Plan

TEXT = {"class": "form-control"}
CHECK = {"class": "form-check-input"}


class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        fields = [
            "name", "price", "billing_interval", "minimum_quantity",
            "available_from", "available_until", "auto_close", "allow_early_close",
            "allow_pause", "allow_renewal", "is_active",
        ]
        widgets = {
            "name": forms.TextInput({**TEXT, "placeholder": "e.g. Business Monthly"}),
            "price": forms.NumberInput({**TEXT, "step": "0.01", "min": "0"}),
            "billing_interval": forms.Select({"class": "form-select"}),
            "minimum_quantity": forms.NumberInput({**TEXT, "min": "1"}),
            "available_from": forms.DateInput({**TEXT, "type": "date"}),
            "available_until": forms.DateInput({**TEXT, "type": "date"}),
            "auto_close": forms.CheckboxInput(CHECK),
            "allow_early_close": forms.CheckboxInput(CHECK),
            "allow_pause": forms.CheckboxInput(CHECK),
            "allow_renewal": forms.CheckboxInput(CHECK),
            "is_active": forms.CheckboxInput(CHECK),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("available_from"), cleaned.get("available_until")
        if start and end and end < start:
            self.add_error("available_until", "Availability end must be on or after the start date.")
        return cleaned
