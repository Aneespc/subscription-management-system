from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.invoicing.models import Invoice

from .models import Payment

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=14, decimal_places=2)


class PaymentError(ValueError):
    pass


def _mark_invoice_paid(invoice, payment):
    from apps.invoicing.services import InvoiceService

    InvoiceService.mark_paid(invoice=invoice, payment=payment)


def calculate_outstanding(invoice):
    paid = invoice.payments.aggregate(total=Coalesce(Sum("amount"), Value(ZERO), output_field=MONEY))["total"]
    return invoice.total_amount - paid


def record_payment(invoice, amount, method, recorded_by, payment_date=None, notes=""):
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        raise PaymentError("Payment amount must be greater than zero.")
    if method not in Payment.PaymentMethod.values:
        raise PaymentError(f"Invalid payment method: {method}")

    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status != Invoice.Status.CONFIRMED:
            raise PaymentError(
                f"Payments can only be recorded against confirmed invoices (this one is {invoice.get_status_display().lower()})."
            )
        outstanding = calculate_outstanding(invoice)
        if amount > outstanding:
            raise PaymentError(f"Amount {amount} exceeds the outstanding balance of {outstanding}.")
        payment = Payment.objects.create(
            payment_number=f"TMP-{timezone.now().timestamp()}",
            invoice=invoice,
            amount=amount,
            payment_method=method,
            payment_date=payment_date or timezone.now(),
            notes=notes,
            recorded_by=recorded_by,
        )
        payment.payment_number = f"PAY-{payment.payment_date.year}-{payment.pk:05d}"
        payment.save(update_fields=["payment_number"])
        if calculate_outstanding(invoice) <= ZERO:
            _mark_invoice_paid(invoice, payment)
    return payment


def outstanding_subquery():
    paid = (
        Payment.objects.filter(invoice=OuterRef("pk"))
        .order_by()
        .values("invoice")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    return Coalesce(Subquery(paid, output_field=MONEY), Value(ZERO), output_field=MONEY)


def get_open_invoices():
    return (
        Invoice.objects.filter(status=Invoice.Status.CONFIRMED)
        .annotate(paid=outstanding_subquery())
        .annotate(outstanding=F("total_amount") - F("paid"))
        .filter(outstanding__gt=0)
    )


def get_overdue_invoices():
    return get_open_invoices().filter(due_date__lt=timezone.localdate())
