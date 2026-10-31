from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.invoicing.models import Invoice

from .models import Payment

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=14, decimal_places=2)


class PaymentError(ValueError):
    """Raised when a payment breaks a business rule."""


def _mark_invoice_paid(invoice, payment):
    # Imported here to avoid circular imports between the invoicing and payments apps
    from apps.invoicing.services import InvoiceService

    InvoiceService.mark_paid(invoice=invoice, payment=payment)


def calculate_outstanding(invoice):
    paid = invoice.payments.aggregate(
        total=Coalesce(Sum("amount"), Value(ZERO), output_field=MONEY)
    )["total"]
    return invoice.total_amount - paid


def record_payment(invoice, amount, method, recorded_by,
                   payment_date=None, transaction_reference="", notes=""):
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        raise PaymentError("Payment amount must be greater than zero.")
    if method not in Payment.PaymentMethod.values:
        raise PaymentError(f"Invalid payment method: {method}")

    with transaction.atomic():
        # Lock the invoice row so two simultaneous payments can't both pass the check
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)

        if invoice.status != Invoice.Status.CONFIRMED:
            raise PaymentError(
                f"Payments are only accepted on CONFIRMED invoices (this one is {invoice.status})."
            )

        outstanding = calculate_outstanding(invoice)
        if amount > outstanding:
            raise PaymentError(f"Amount {amount} exceeds the outstanding balance {outstanding}.")

        payment = Payment.objects.create(
            payment_number=f"TMP-{uuid4().hex[:12]}",
            invoice=invoice,
            amount=amount,
            payment_method=method,
            payment_date=payment_date or timezone.now(),
            transaction_reference=transaction_reference,
            notes=notes,
            recorded_by=recorded_by,
        )
        payment.payment_number = f"PAY-{payment.payment_date.year}-{payment.pk:05d}"
        payment.save(update_fields=["payment_number"])

        # Only a fully paid invoice moves to PAID, and Member 3's service owns that transition
        if calculate_outstanding(invoice) == 0:
            _mark_invoice_paid(invoice, payment)

    return payment


def get_overdue_invoices():
    """CONFIRMED invoices past their due date with a balance left.

    Uses a subquery instead of a join, so the result can be counted and
    summed in a single query (the dashboard relies on this).
    """
    paid = (
        Payment.objects.filter(invoice=OuterRef("pk"))
        .order_by()
        .values("invoice")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    return (
        Invoice.objects.filter(
            status=Invoice.Status.CONFIRMED, due_date__lt=timezone.localdate()
        )
        .annotate(paid=Coalesce(Subquery(paid, output_field=MONEY), Value(ZERO), output_field=MONEY))
        .annotate(outstanding=F("total_amount") - F("paid"))
        .filter(outstanding__gt=0)
    )


def reconcile_payment(payment):
    """Re-check a payment's invoice and fix or flag status mismatches."""
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
        outstanding = calculate_outstanding(invoice)
        issues = []

        if outstanding < 0:
            issues.append("Overpaid: payments exceed the invoice total.")
        if outstanding <= 0 and invoice.status == Invoice.Status.CONFIRMED:
            _mark_invoice_paid(invoice, payment)
            invoice.refresh_from_db()
        elif outstanding > 0 and invoice.status == Invoice.Status.PAID:
            issues.append("Invoice is PAID but still has an outstanding balance.")

    return {"invoice": invoice.invoice_number, "outstanding": outstanding,
            "status": invoice.status, "issues": issues}