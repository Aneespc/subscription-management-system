from django import forms
from django.forms import inlineformset_factory
from .models import Quotation, QuotationLine, QuotationTemplate, QuotationTemplateLine
from apps.accounts.models import CustomerProfile
from apps.products.models import Product, ProductVariant
from apps.plans.models import Plan


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


class QuotationTemplateLineForm(forms.ModelForm):
    class Meta:
        model = QuotationTemplateLine
        fields = ["product", "variant", "quantity"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select product-select"}),
            "variant": forms.Select(attrs={"class": "form-select variant-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }


QuotationTemplateLineFormSet = inlineformset_factory(
    QuotationTemplate,
    QuotationTemplateLine,
    form=QuotationTemplateLineForm,
    extra=1,
    can_delete=True
)


class TemplateSelectForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=CustomerProfile.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"})
    )
    template = forms.ModelChoiceField(
        queryset=QuotationTemplate.objects.filter(is_active=True),
        widget=forms.Select(attrs={"class": "form-select"})
    )
    payment_terms = forms.ChoiceField(
        choices=Quotation.PaymentTerms.choices,
        initial=Quotation.PaymentTerms.NET_30,
        widget=forms.Select(attrs={"class": "form-select"})
    )


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = [
            "customer", "template", "issue_date", "expiry_date",
            "payment_terms", "status", "notes"
        ]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "template": forms.Select(attrs={"class": "form-select"}),
            "issue_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "payment_terms": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class QuotationLineForm(forms.ModelForm):
    class Meta:
        model = QuotationLine
        fields = ["product", "variant", "quantity", "unit_price", "tax_rate"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select product-select"}),
            "variant": forms.Select(attrs={"class": "form-select variant-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control quantity-input", "min": 1}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control price-input", "step": "0.01"}),
            "tax_rate": forms.NumberInput(attrs={"class": "form-control tax-input", "step": "0.01"}),
        }


QuotationLineFormSet = inlineformset_factory(
    Quotation,
    QuotationLine,
    form=QuotationLineForm,
    extra=1,
    can_delete=True
)
