import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.mixins import is_staff_user
from apps.invoicing.models import Invoice

from . import gateway
from .models import GatewayOrder


def customer_invoice(request, pk):
    qs = Invoice.objects.select_related("customer", "customer__user")
    if not is_staff_user(request.user):
        qs = qs.filter(customer__user=request.user)
    return get_object_or_404(qs, pk=pk)


class CheckoutView(LoginRequiredMixin, View):
    template_name = "payments/checkout.html"

    def post(self, request, invoice_pk):
        invoice = customer_invoice(request, invoice_pk)
        if not gateway.enabled():
            messages.error(request, "Online payments are not configured yet.")
            return redirect("invoicing:invoice_detail", pk=invoice.pk)
        try:
            with transaction.atomic():
                order = gateway.create_order(invoice, request.user)
        except gateway.GatewayError as exc:
            messages.error(request, str(exc))
            return redirect("invoicing:invoice_detail", pk=invoice.pk)
        except Exception:
            messages.error(request, "Could not start the payment. Please try again.")
            return redirect("invoicing:invoice_detail", pk=invoice.pk)
        return render(
            request,
            self.template_name,
            {
                "invoice": invoice,
                "order": order,
                "key_id": settings.RAZORPAY_KEY_ID,
                "amount_paise": gateway.to_paise(order.amount),
                "currency": order.currency,
                "customer": invoice.customer,
                "callback_url": reverse("payments:razorpay_callback", args=[order.pk]),
            },
        )


class CallbackView(LoginRequiredMixin, View):
    def post(self, request, order_pk):
        order = get_object_or_404(GatewayOrder.objects.select_related("invoice", "invoice__customer"), pk=order_pk)
        if not is_staff_user(request.user) and order.invoice.customer.user_id != request.user.pk:
            return HttpResponseBadRequest("Unknown order.")
        payment_id = request.POST.get("razorpay_payment_id", "")
        signature = request.POST.get("razorpay_signature", "")
        order_id = request.POST.get("razorpay_order_id", "")
        if request.POST.get("error"):
            gateway.fail_order(order, request.POST.get("error"))
            messages.error(request, f"Payment was not completed: {request.POST.get('error')}")
            return redirect("invoicing:invoice_detail", pk=order.invoice_id)
        if order_id != order.order_id or not gateway.verify_checkout_signature(order_id, payment_id, signature):
            gateway.fail_order(order, "Signature verification failed")
            messages.error(request, "We could not verify this payment. No amount was recorded.")
            return redirect("invoicing:invoice_detail", pk=order.invoice_id)
        try:
            gateway.settle_order(order, payment_id)
        except gateway.GatewayError as exc:
            messages.error(request, str(exc))
            return redirect("invoicing:invoice_detail", pk=order.invoice_id)
        order.invoice.refresh_from_db()
        suffix = " The invoice is now fully paid." if order.invoice.status == Invoice.Status.PAID else ""
        messages.success(request, f"Payment received. Thank you.{suffix}")
        return redirect("invoicing:invoice_detail", pk=order.invoice_id)


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):
    def post(self, request):
        signature = request.headers.get("X-Razorpay-Signature", "")
        if not gateway.verify_webhook_signature(request.body, signature):
            return HttpResponse("invalid signature", status=400)
        try:
            payload = json.loads(request.body)
            entity = payload["payload"]["payment"]["entity"]
        except (ValueError, KeyError):
            return HttpResponse("malformed payload", status=400)
        order = GatewayOrder.objects.filter(order_id=entity.get("order_id", "")).first()
        if order is None:
            return JsonResponse({"status": "ignored"})
        event = payload.get("event", "")
        if event == "payment.captured" and order.status != GatewayOrder.Status.PAID:
            try:
                gateway.settle_order(order, entity.get("id", ""), amount=(entity.get("amount") or 0) / 100)
            except gateway.GatewayError:
                pass
        elif event == "payment.failed" and order.status == GatewayOrder.Status.CREATED:
            gateway.fail_order(order, (entity.get("error_description") or "Payment failed"))
        return JsonResponse({"status": "ok"})
