from decimal import Decimal

from django import forms
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounts.models import CustomerProfile
from apps.invoicing.models import Invoice
from apps.payments.models import Payment
from apps.payments.services import get_open_invoices, get_overdue_invoices
from apps.subscriptions.models import Subscription

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=14, decimal_places=2)


class DashboardFilterForm(forms.Form):
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
    method = forms.ChoiceField(
        required=False,
        choices=[("", "All methods")] + Payment.PaymentMethod.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    customer = forms.ModelChoiceField(
        required=False,
        queryset=CustomerProfile.objects.order_by("company_name"),
        empty_label="All customers",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("date_from") and cleaned.get("date_to") and cleaned["date_to"] < cleaned["date_from"]:
            self.add_error("date_to", "End date must be on or after the start date.")
        return cleaned


def _sum(field):
    return Coalesce(Sum(field), Value(ZERO), output_field=MONEY)


def filter_payments(data):
    qs = Payment.objects.all()
    if data.get("date_from"):
        qs = qs.filter(payment_date__date__gte=data["date_from"])
    if data.get("date_to"):
        qs = qs.filter(payment_date__date__lte=data["date_to"])
    if data.get("method"):
        qs = qs.filter(payment_method=data["method"])
    if data.get("customer"):
        qs = qs.filter(invoice__customer=data["customer"])
    return qs


def filter_invoices(data):
    qs = Invoice.objects.all()
    if data.get("date_from"):
        qs = qs.filter(issue_date__gte=data["date_from"])
    if data.get("date_to"):
        qs = qs.filter(issue_date__lte=data["date_to"])
    if data.get("customer"):
        qs = qs.filter(customer=data["customer"])
    return qs


def filter_subscriptions(data):
    qs = Subscription.objects.all()
    if data.get("customer"):
        qs = qs.filter(customer=data["customer"])
    return qs


def get_summary(data):
    today = timezone.localdate()
    revenue = filter_payments(data).aggregate(total=_sum("amount"), count=Count("id"))
    open_totals = get_open_invoices().aggregate(count=Count("id"), amount=_sum("outstanding"))
    overdue = get_overdue_invoices().aggregate(count=Count("id"), amount=_sum("outstanding"))
    subs = filter_subscriptions(data).aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=Subscription.Status.ACTIVE)),
        paused=Count("id", filter=Q(status=Subscription.Status.PAUSED)),
    )
    invoices = filter_invoices(data).aggregate(
        total=Count("id"),
        draft=Count("id", filter=Q(status=Invoice.Status.DRAFT)),
        paid=Coalesce(Sum("total_amount", filter=Q(status=Invoice.Status.PAID)), Value(ZERO), output_field=MONEY),
    )
    return {
        "revenue_received": revenue["total"],
        "payments_count": revenue["count"],
        "outstanding_amount": open_totals["amount"],
        "outstanding_invoices": open_totals["count"],
        "overdue_invoices": overdue["count"],
        "overdue_amount": overdue["amount"],
        "total_invoices": invoices["total"],
        "draft_invoices": invoices["draft"],
        "paid_amount": invoices["paid"],
        "active_subscriptions": subs["active"],
        "paused_subscriptions": subs["paused"],
        "total_subscriptions": subs["total"],
        "total_customers": CustomerProfile.objects.count(),
        "due_for_billing": Subscription.objects.filter(status=Subscription.Status.ACTIVE, next_billing_date__lte=today).count(),
    }


def payments_by_method(data):
    return list(
        filter_payments(data).values("payment_method").annotate(total=_sum("amount"), count=Count("id")).order_by("-total")
    )
