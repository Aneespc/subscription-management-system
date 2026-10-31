from decimal import Decimal

from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth, TruncQuarter, TruncYear
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from apps.payments.models import Invoice, Payment
from apps.payments.services import get_overdue_invoices

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=14, decimal_places=2)
TRUNC = {"month": TruncMonth, "quarter": TruncQuarter, "year": TruncYear}


def _sum(field):
    return Coalesce(Sum(field), Value(ZERO), output_field=MONEY)


def _date(params, key):
    raw = params.get(key)
    if not raw:
        return None
    value = parse_date(raw)
    if value is None:
        raise ValidationError({key: "Use YYYY-MM-DD."})
    return value


def filter_payments(params):
    qs = Payment.objects.all()
    if d := _date(params, "date_from"):
        qs = qs.filter(payment_date__date__gte=d)
    if d := _date(params, "date_to"):
        qs = qs.filter(payment_date__date__lte=d)
    if params.get("method"):
        qs = qs.filter(payment_method=params["method"])
    if params.get("invoice_status"):
        qs = qs.filter(invoice__status=params["invoice_status"])
    # TODO: customer filter once Invoice has the real `customer` FK
    return qs


def revenue_by_period(params):
    trunc = TRUNC.get(params.get("group", "month"), TruncMonth)
    return list(
        filter_payments(params)
        .annotate(period=trunc("payment_date"))
        .values("period")
        .annotate(total=_sum("amount"), count=Count("id"))
        .order_by("period")
    )


def payments_by_method(params):
    return list(
        filter_payments(params)
        .values("payment_method")
        .annotate(total=_sum("amount"), count=Count("id"))
        .order_by("-total")
    )


def get_summary(params):
    revenue = filter_payments(params).aggregate(total=_sum("amount"), count=Count("id"))

    # Two separate aggregates: joining payments to invoices would repeat each invoice total
    billed = Invoice.objects.filter(status=Invoice.Status.CONFIRMED).aggregate(t=_sum("total_amount"))["t"]
    paid_on_open = Payment.objects.filter(invoice__status=Invoice.Status.CONFIRMED).aggregate(t=_sum("amount"))["t"]

    overdue = list(get_overdue_invoices())

    return {
        "revenue_received": revenue["total"],
        "payments_count": revenue["count"],
        "outstanding_amount": billed - paid_on_open,
        "total_invoices": Invoice.objects.count(),
        "overdue_invoices": len(overdue),
        "overdue_amount": sum((i.outstanding for i in overdue), ZERO),
        # Placeholders until Member 2's models land:
        "total_customers": None,
        "active_subscriptions": None,
        "total_subscriptions": None,
        "mrr": None,
    }


def get_report(params):
    return {
        "summary": get_summary(params),
        "revenue_by_period": revenue_by_period(params),
        "payments_by_method": payments_by_method(params),
    }