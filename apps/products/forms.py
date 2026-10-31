from django import forms
from django.forms import inlineformset_factory

from .models import Product, ProductVariant, Tax

TEXT = {"class": "form-control"}


class ProductForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tax"].queryset = Tax.objects.filter(is_active=True)
        self.fields["tax"].empty_label = "No tax"

    class Meta:
        model = Product
        fields = ["name", "product_type", "sales_price", "cost_price", "tax", "notes", "is_active"]
        widgets = {
            "name": forms.TextInput({**TEXT, "placeholder": "e.g. Brightloop Business ERP"}),
            "product_type": forms.Select({"class": "form-select"}),
            "tax": forms.Select({"class": "form-select"}),
            "sales_price": forms.NumberInput({**TEXT, "step": "0.01", "min": "0"}),
            "cost_price": forms.NumberInput({**TEXT, "step": "0.01", "min": "0"}),
            "notes": forms.Textarea({**TEXT, "rows": 3}),
            "is_active": forms.CheckboxInput({"class": "form-check-input"}),
        }


class ProductVariantForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["price_extra"].required = False

    def has_changed(self):
        data = self.data if self.is_bound else {}
        name = data.get(self.add_prefix("attribute_name"), "").strip()
        value = data.get(self.add_prefix("attribute_value"), "").strip()
        if not self.instance.pk and not name and not value:
            return False
        return super().has_changed()

    def clean_price_extra(self):
        value = self.cleaned_data.get("price_extra") or 0
        if value < 0:
            raise forms.ValidationError("Price extra cannot be negative.")
        return value

    class Meta:
        model = ProductVariant
        fields = ["attribute_name", "attribute_value", "price_extra"]
        widgets = {
            "attribute_name": forms.TextInput({**TEXT, "placeholder": "Brand"}),
            "attribute_value": forms.TextInput({**TEXT, "placeholder": "Odoo"}),
            "price_extra": forms.NumberInput({**TEXT, "step": "0.01"}),
        }


ProductVariantFormSet = inlineformset_factory(
    Product, ProductVariant, form=ProductVariantForm, extra=1, can_delete=True
)
