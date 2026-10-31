import hashlib
import hmac
import logging
from decimal import Decimal

import razorpay
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.invoicing.models import Invoice

from .models import GatewayOrder, Payment
from .services import PaymentError, calculate_outstanding, record_payment

logger = logging.getLogger(__name__)


class GatewayError(Exception):
    pass


def enabled():
    return settings.RAZORPAY_ENABLED


def client():
    if not enabled():
        raise GatewayError("Online payments are not configured.")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def to_paise(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def create_order(invoice, user):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != Invoice.Status.CONFIRMED:
        raise GatewayError("Only confirmed invoices can be paid online.")
    outstanding = calculate_outstanding(invoice)
    if outstanding <= 0:
        raise GatewayError("This invoice has nothing outstanding.")
    data = client().order.create(
        {
            "amount": to_paise(outstanding),
            "currency": settings.CURRENCY_CODE,
            "receipt": invoice.invoice_number,
            "notes": {"invoice": invoice.invoice_number, "customer": invoice.customer.company_name},
        }
    )
    return GatewayOrder.objects.create(
        invoice=invoice,
        order_id=data["id"],
        amount=outstanding,
        currency=data.get("currency", settings.CURRENCY_CODE),
        created_by=user,
    )


def verify_checkout_signature(order_id, payment_id, signature):
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def verify_webhook_signature(body, signature):
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def settle_order(order, payment_id, amount=None):
    with transaction.atomic():
        order = GatewayOrder.objects.select_for_update().get(pk=order.pk)
        if order.status == GatewayOrder.Status.PAID:
            return order
        amount = Decimal(amount) if amount is not None else order.amount
        try:
            payment = record_payment(
                invoice=order.invoice,
                amount=amount,
                method=Payment.PaymentMethod.ONLINE,
                recorded_by=order.created_by,
                payment_date=timezone.now(),
                notes=f"Razorpay payment {payment_id} for order {order.order_id}",
            )
        except PaymentError as exc:
            order.status = GatewayOrder.Status.FAILED
            order.error_message = str(exc)[:255]
            order.save(update_fields=["status", "error_message", "updated_at"])
            raise GatewayError(str(exc))
        order.status = GatewayOrder.Status.PAID
        order.gateway_payment_id = payment_id
        order.payment = payment
        order.error_message = ""
        order.save(update_fields=["status", "gateway_payment_id", "payment", "error_message", "updated_at"])
        return order


def fail_order(order, message):
    order.status = GatewayOrder.Status.FAILED
    order.error_message = (message or "Payment failed")[:255]
    order.save(update_fields=["status", "error_message", "updated_at"])
    return order
