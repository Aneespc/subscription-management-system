from django import forms
from django.forms import inlineformset_factory

from apps.accounts.models import CustomerProfile
from apps.plans.models import Plan
from apps.products.models import Product, ProductVariant

from .models import Quotation, QuotationLine, QuotationTemplate, QuotationTemplateLine


class IgnoreBlankLineMixin:
    def has_changed(self):
        if not self.instance.pk and self.is_bound and not self.data.get(self.add_prefix("product")):
            return False
        return super().has_changed()


def variant_choices(queryset):
    return [("", "No variant")] + [
        (v.pk, f"{v.product.name} - {v.attribute_name}: {v.attribute_value} (+₹{v.price_extra})") for v in queryset
    ]


class QuotationTemplateForm(forms.ModelForm):
    class Meta:
        model = QuotationTemplate
        fields = ["name", "plan", "validity_days", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Standard Business Tier"}),
            "plan": forms.Select(attrs={"class": "form-select"}),
            "validity_days": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = Plan.objects.filter(is_active=True)


class QuotationTemplateLineForm(IgnoreBlankLineMixin, forms.ModelForm):
    class Meta:
        model = QuotationTemplateLine
        fields = ["product", "variant", "quantity"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select product-select"}),
            "variant": forms.Select(attrs={"class": "form-select variant-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True)
        self.fields["variant"].queryset = ProductVariant.objects.select_related("product")
        self.fields["variant"].widget.choices = variant_choices(self.fields["variant"].queryset)

    def clean(self):
        cleaned = super().clean()
        product, variant = cleaned.get("product"), cleaned.get("variant")
        if product and variant and variant.product_id != product.pk:
            self.add_error("variant", "This variant does not belong to the selected product.")
        return cleaned


class RequireOneLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if not [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]:
            raise forms.ValidationError("Add at least one product line.")


QuotationTemplateLineFormSet = inlineformset_factory(
    QuotationTemplate, QuotationTemplateLine, form=QuotationTemplateLineForm, formset=RequireOneLineFormSet, extra=1, can_delete=True
)


class TemplateSelectForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=CustomerProfile.objects.order_by("company_name"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    template = forms.ModelChoiceField(
        queryset=QuotationTemplate.objects.filter(is_active=True),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    payment_terms = forms.ChoiceField(
        choices=Quotation.PaymentTerms.choices,
        initial=Quotation.PaymentTerms.NET_30,
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ["customer", "plan", "template", "issue_date", "expiry_date", "payment_terms"]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "plan": forms.Select(attrs={"class": "form-select"}),
            "template": forms.Select(attrs={"class": "form-select"}),
            "issue_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "payment_terms": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = CustomerProfile.objects.order_by("company_name")
        self.fields["plan"].queryset = Plan.objects.filter(is_active=True)
        self.fields["plan"].required = True
        self.fields["template"].queryset = QuotationTemplate.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("issue_date"), cleaned.get("expiry_date")
        if start and end and end < start:
            self.add_error("expiry_date", "Expiry date must be on or after the issue date.")
        template, plan = cleaned.get("template"), cleaned.get("plan")
        if template and plan and template.plan_id != plan.pk:
            self.add_error("template", "This template belongs to a different plan.")
        return cleaned


class QuotationLineForm(IgnoreBlankLineMixin, forms.ModelForm):
    class Meta:
        model = QuotationLine
        fields = ["product", "variant", "quantity", "unit_price"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select product-select"}),
            "variant": forms.Select(attrs={"class": "form-select variant-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control quantity-input", "min": 1}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control price-input", "step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True)
        self.fields["variant"].queryset = ProductVariant.objects.select_related("product")
        self.fields["variant"].widget.choices = variant_choices(self.fields["variant"].queryset)
        self.fields["unit_price"].required = False

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


QuotationLineFormSet = inlineformset_factory(
    Quotation, QuotationLine, form=QuotationLineForm, formset=RequireOneLineFormSet, extra=1, can_delete=True
)
