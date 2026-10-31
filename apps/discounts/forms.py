from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError

from apps.discounts.models import Discount


class DiscountForm(forms.ModelForm):
    class Meta:
        model = Discount
        fields = [
            "name",
            "discount_type",
            "value",
            "minimum_purchase",
            "minimum_quantity",
            "start_date",
            "end_date",
            "usage_limit",
            "applies_to",
            "products",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Summer Special"}),
            "discount_type": forms.Select(attrs={"class": "form-select"}),
            "value": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "e.g. 15.00"}),
            "minimum_purchase": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "Optional, e.g. 50.00"}),
            "minimum_quantity": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Optional, e.g. 2"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "usage_limit": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Leave empty for unlimited"}),
            "applies_to": forms.Select(attrs={"class": "form-select"}),
            "products": forms.SelectMultiple(attrs={"class": "form-select", "size": "4"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        discount_type = cleaned_data.get("discount_type")
        value = cleaned_data.get("value")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        minimum_purchase = cleaned_data.get("minimum_purchase")
        applies_to = cleaned_data.get("applies_to")
        products = cleaned_data.get("products")

        if value is not None and value <= Decimal("0.00"):
            self.add_error("value", "Discount value must be greater than zero.")

        if discount_type == Discount.DiscountType.PERCENTAGE and value is not None:
            if value < Decimal("0.00") or value > Decimal("100.00"):
                self.add_error("value", "Percentage discount must be between 0% and 100%.")

        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must be on or after start date.")

        if minimum_purchase is not None and minimum_purchase < Decimal("0.00"):
            self.add_error("minimum_purchase", "Minimum purchase cannot be negative.")

        if applies_to == Discount.AppliesTo.PRODUCTS and not products:
            self.add_error("products", "Select at least one product for a product-specific discount.")

        usage_limit = cleaned_data.get("usage_limit")
        if usage_limit is not None and self.instance.pk and usage_limit < self.instance.usage_count:
            self.add_error("usage_limit", f"This discount has already been used {self.instance.usage_count} times.")

        return cleaned_data


class DiscountFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Search by discount name..."}),
    )
    discount_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Types")] + Discount.DiscountType.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    is_active = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses"), ("true", "Active Only"), ("false", "Inactive Only")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )

