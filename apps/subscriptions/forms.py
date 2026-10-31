from django import forms
from django.forms import inlineformset_factory

from apps.accounts.models import CustomerProfile
from apps.plans.models import Plan
from apps.products.models import Product, ProductVariant

from .models import Subscription, SubscriptionLine


class IgnoreBlankLineMixin:
    def has_changed(self):
        if not self.instance.pk and self.is_bound and not self.data.get(self.add_prefix("product")):
            return False
        return super().has_changed()


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ["customer", "plan", "start_date", "expiry_date", "payment_terms", "status"]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "plan": forms.Select(attrs={"class": "form-select"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "payment_terms": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = CustomerProfile.objects.select_related("user").order_by("company_name")
        self.fields["plan"].queryset = Plan.objects.filter(is_active=True).order_by("price")
        self.fields["status"].choices = [
            (value, label) for value, label in Subscription.Status.choices
            if value in ("DRAFT", "CONFIRMED", "ACTIVE")
        ] if not (self.instance and self.instance.pk) else Subscription.Status.choices

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("expiry_date")
        if start and end and end < start:
            self.add_error("expiry_date", "Expiry date must be on or after the start date.")
        return cleaned


class SubscriptionLineForm(IgnoreBlankLineMixin, forms.ModelForm):
    class Meta:
        model = SubscriptionLine
        fields = ["product", "variant", "quantity", "unit_price"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select product-select"}),
            "variant": forms.Select(attrs={"class": "form-select variant-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control quantity-input", "min": 1}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control price-input", "step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True).order_by("name")
        self.fields["variant"].queryset = ProductVariant.objects.select_related("product").order_by("product__name")
        self.fields["unit_price"].required = False
        self.fields["variant"].widget.choices = [("", "No variant")] + [
            (v.pk, f"{v.product.name} - {v.attribute_name}: {v.attribute_value} (+{v.price_extra})")
            for v in self.fields["variant"].queryset
        ]

    def clean(self):
        cleaned = super().clean()
        product, variant = cleaned.get("product"), cleaned.get("variant")
        if product and variant and variant.product_id != product.pk:
            self.add_error("variant", "This variant does not belong to the selected product.")
        if cleaned.get("unit_price") is None:
            cleaned["unit_price"] = 0
        if product:
            self.instance.tax_rate = product.tax_rate
        return cleaned


class RequireOneLineFormSet(forms.BaseInlineFormSet):
    def live_forms(self):
        return [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]

    def total_quantity(self):
        return sum(f.cleaned_data.get("quantity") or 0 for f in self.live_forms())

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if not self.live_forms():
            raise forms.ValidationError("Add at least one product line.")


SubscriptionLineFormSet = inlineformset_factory(
    Subscription, SubscriptionLine, form=SubscriptionLineForm, formset=RequireOneLineFormSet, extra=1, can_delete=True
)


class SubscriptionRenewForm(forms.Form):
    additional_days = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 30, 365"}),
    )


class CheckoutLineForm(IgnoreBlankLineMixin, forms.ModelForm):
    class Meta:
        model = SubscriptionLine
        fields = ["product", "variant", "quantity"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select product-select"}),
            "variant": forms.Select(attrs={"class": "form-select variant-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control quantity-input", "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True).select_related("tax").order_by("name")
        self.fields["product"].widget.choices = [("", "Choose a product")] + [
            (p.pk, f"{p.name} - {p.sales_price}") for p in self.fields["product"].queryset
        ]
        self.fields["variant"].queryset = ProductVariant.objects.select_related("product").order_by("product__name")
        self.fields["variant"].widget.choices = [("", "No variant")] + [
            (v.pk, f"{v.attribute_name}: {v.attribute_value} (+{v.price_extra})") for v in self.fields["variant"].queryset
        ]

    def clean(self):
        cleaned = super().clean()
        product, variant = cleaned.get("product"), cleaned.get("variant")
        if product and variant and variant.product_id != product.pk:
            self.add_error("variant", "This variant does not belong to the selected product.")
        if product:
            self.instance.tax_rate = product.tax_rate
        return cleaned


CheckoutLineFormSet = inlineformset_factory(
    Subscription, SubscriptionLine, form=CheckoutLineForm, formset=RequireOneLineFormSet, extra=1, can_delete=True
)
