from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.accounts.mixins import StaffRequiredMixin
from apps.invoicing.models import Invoice

from .forms import PaymentFilterForm, PaymentForm
from .models import Payment
from .services import PaymentError, calculate_outstanding, get_overdue_invoices, record_payment


class PaymentListView(StaffRequiredMixin, ListView):
    template_name = "payments/payment_list.html"
    context_object_name = "payments"
    paginate_by = 25

    def get_queryset(self):
        qs = Payment.objects.select_related("invoice", "invoice__customer", "recorded_by")
        form = PaymentFilterForm(self.request.GET)
        if form.is_valid():
            data = form.cleaned_data
            if data.get("q"):
                q = data["q"]
                qs = qs.filter(
                    Q(payment_number__icontains=q)
                    | Q(invoice__invoice_number__icontains=q)
                    | Q(invoice__customer__company_name__icontains=q)
                )
            if data.get("method"):
                qs = qs.filter(payment_method=data["method"])
            if data.get("date_from"):
                qs = qs.filter(payment_date__date__gte=data["date_from"])
            if data.get("date_to"):
                qs = qs.filter(payment_date__date__lte=data["date_to"])
        return qs.order_by("-payment_date", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        context["filter_form"] = PaymentFilterForm(self.request.GET)
        context["kpis"] = {
            **Payment.objects.aggregate(
                total=Sum("amount"),
                count=Count("id"),
                month=Sum("amount", filter=Q(payment_date__year=today.year, payment_date__month=today.month)),
            ),
            **get_overdue_invoices().aggregate(overdue_count=Count("id"), overdue_amount=Sum("outstanding")),
        }
        context["open_invoices"] = (
            Invoice.objects.filter(status=Invoice.Status.CONFIRMED)
            .select_related("customer")
            .order_by("due_date")[:8]
        )
        return context


class PaymentRecordView(StaffRequiredMixin, View):
    template_name = "payments/payment_form.html"

    def get_invoice(self, pk):
        return get_object_or_404(Invoice.objects.select_related("customer", "customer__user"), pk=pk)

    def get(self, request, invoice_pk):
        invoice = self.get_invoice(invoice_pk)
        outstanding = calculate_outstanding(invoice)
        form = PaymentForm(initial={"amount": outstanding, "payment_date": timezone.now()})
        return render(
            request,
            self.template_name,
            {"invoice": invoice, "form": form, "outstanding": outstanding, "paid": invoice.total_amount - outstanding},
        )

    def post(self, request, invoice_pk):
        invoice = self.get_invoice(invoice_pk)
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                payment = record_payment(
                    invoice=invoice,
                    amount=form.cleaned_data["amount"],
                    method=form.cleaned_data["payment_method"],
                    recorded_by=request.user,
                    payment_date=form.cleaned_data["payment_date"],
                    notes=form.cleaned_data["notes"],
                )
                invoice.refresh_from_db()
                suffix = " Invoice is now fully paid." if invoice.status == Invoice.Status.PAID else ""
                messages.success(request, f"Payment {payment.payment_number} recorded.{suffix}")
                return redirect("invoicing:invoice_detail", pk=invoice.pk)
            except PaymentError as exc:
                form.add_error(None, str(exc))
        outstanding = calculate_outstanding(invoice)
        return render(
            request,
            self.template_name,
            {"invoice": invoice, "form": form, "outstanding": outstanding, "paid": invoice.total_amount - outstanding},
        )
