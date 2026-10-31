from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.accounts.mixins import AdminRequiredMixin, StaffRequiredMixin, is_staff_user
from apps.invoicing.forms import InvoiceFilterForm, TaxForm
from apps.invoicing.models import Invoice
from apps.invoicing.services import InvoiceService
from apps.payments.services import calculate_outstanding
from apps.products.models import Tax


def scoped_invoices(user):
    qs = Invoice.objects.all()
    if not is_staff_user(user):
        qs = qs.filter(customer__user=user)
    return qs


class InvoiceListView(LoginRequiredMixin, ListView):
    template_name = "invoicing/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 20

    def get_queryset(self):
        qs = scoped_invoices(self.request.user).select_related("customer", "customer__user", "subscription")
        form = InvoiceFilterForm(self.request.GET)
        if form.is_valid():
            data = form.cleaned_data
            if data.get("q"):
                q = data["q"]
                qs = qs.filter(
                    Q(invoice_number__icontains=q)
                    | Q(customer__company_name__icontains=q)
                    | Q(customer__user__email__icontains=q)
                    | Q(subscription__subscription_number__icontains=q)
                )
            if data.get("status"):
                qs = qs.filter(status=data["status"])
            if data.get("customer") and is_staff_user(self.request.user):
                qs = qs.filter(customer=data["customer"])
            if data.get("date_from"):
                qs = qs.filter(issue_date__gte=data["date_from"])
            if data.get("date_to"):
                qs = qs.filter(issue_date__lte=data["date_to"])
            if data.get("overdue_only"):
                qs = qs.filter(status=Invoice.Status.CONFIRMED, due_date__lt=timezone.localdate())
        return qs.order_by("-issue_date", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = scoped_invoices(self.request.user)
        today = timezone.localdate()
        context["filter_form"] = InvoiceFilterForm(self.request.GET)
        context["is_staff_user"] = is_staff_user(self.request.user)
        context["kpis"] = base.aggregate(
            total=Count("id"),
            draft=Count("id", filter=Q(status="DRAFT")),
            outstanding=Sum("total_amount", filter=Q(status="CONFIRMED")),
            overdue=Count("id", filter=Q(status="CONFIRMED", due_date__lt=today)),
            paid=Sum("total_amount", filter=Q(status="PAID")),
        )
        return context


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    template_name = "invoicing/invoice_detail.html"
    context_object_name = "invoice"

    def get_queryset(self):
        return scoped_invoices(self.request.user).select_related(
            "customer", "customer__user", "subscription", "subscription__plan"
        ).prefetch_related(
            "lines__product", "lines__tax", "tax_lines", "discount_usages__discount", "payments__recorded_by"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_manage"] = is_staff_user(self.request.user)
        context["outstanding"] = calculate_outstanding(self.object)
        context["paid"] = self.object.total_amount - context["outstanding"]
        context["can_pay_online"] = (
            settings.RAZORPAY_ENABLED
            and self.object.status == Invoice.Status.CONFIRMED
            and context["outstanding"] > 0
        )
        context["gateway_orders"] = self.object.gateway_orders.all()[:10]
        context["payments"] = self.object.payments.all().order_by("-payment_date")
        return context


class BillingRunView(StaffRequiredMixin, View):
    template_name = "invoicing/billing_run.html"

    def get(self, request):
        from apps.subscriptions.models import Subscription

        today = timezone.localdate()
        due = (
            Subscription.objects.filter(status=Subscription.Status.ACTIVE, next_billing_date__lte=today)
            .select_related("customer", "plan")
            .order_by("next_billing_date")
        )
        return render(request, self.template_name, {"due_subscriptions": due[:200], "due_count": due.count(), "today": today})

    def post(self, request):
        result = InvoiceService.generate_due_invoices()
        if result["created"]:
            messages.success(request, f"Billing run complete: {result['created']} invoice(s) created.")
        else:
            messages.info(request, "Billing run complete: nothing was due.")
        if result["failed"]:
            messages.error(request, f"{result['failed']} subscription(s) failed to bill. Check the logs.")
        if result["auto_closed"]:
            messages.info(request, f"{result['auto_closed']} expired subscription(s) closed automatically.")
        return redirect("invoicing:invoice_list")


class InvoiceConfirmView(StaffRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        try:
            InvoiceService.confirm(invoice)
            messages.success(request, f"Invoice {invoice.invoice_number} confirmed.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("invoicing:invoice_detail", pk=pk)


class InvoiceCancelView(StaffRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        try:
            InvoiceService.cancel(invoice)
            messages.warning(request, f"Invoice {invoice.invoice_number} cancelled.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("invoicing:invoice_detail", pk=pk)


class InvoiceSendView(StaffRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        try:
            InvoiceService.send(invoice)
            messages.success(request, f"Invoice {invoice.invoice_number} emailed to {invoice.customer.contact_email}.")
        except Exception as exc:
            messages.error(request, f"Failed to send invoice: {exc}")
        return redirect("invoicing:invoice_detail", pk=pk)


class InvoicePrintView(LoginRequiredMixin, DetailView):
    template_name = "invoicing/invoice_print.html"
    context_object_name = "invoice"

    def get_queryset(self):
        return scoped_invoices(self.request.user).select_related("customer", "customer__user", "subscription")


class TaxListView(AdminRequiredMixin, ListView):
    model = Tax
    template_name = "invoicing/tax_list.html"
    context_object_name = "taxes"
    paginate_by = 25
    ordering = ["name"]


class TaxCreateView(AdminRequiredMixin, CreateView):
    model = Tax
    form_class = TaxForm
    template_name = "invoicing/tax_form.html"
    success_url = reverse_lazy("invoicing:tax_list")

    def form_valid(self, form):
        messages.success(self.request, f"Tax rate {form.cleaned_data['name']} created.")
        return super().form_valid(form)


class TaxUpdateView(AdminRequiredMixin, UpdateView):
    model = Tax
    form_class = TaxForm
    template_name = "invoicing/tax_form.html"
    success_url = reverse_lazy("invoicing:tax_list")

    def form_valid(self, form):
        messages.success(self.request, f"Tax rate {form.cleaned_data['name']} updated.")
        return super().form_valid(form)
