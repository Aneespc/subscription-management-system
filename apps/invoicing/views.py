from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
)

from apps.invoicing.forms import InvoiceFilterForm, InvoiceGenerateForm, TaxForm
from apps.invoicing.models import Invoice, Tax
from apps.invoicing.permissions import AdminRequiredMixin, StaffOrAdminRequiredMixin
from apps.invoicing.services import InvoiceService


class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = "invoicing/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        qs = (
            Invoice.objects.select_related("customer", "customer__user", "subscription")
            .prefetch_related("lines")
            .order_by("-issue_date", "-id")
        )

        # Customer isolation: customers can ONLY see their own invoices
        if not (getattr(user, "is_staff_role", False) or user.is_staff or user.is_superuser):
            qs = qs.filter(customer__user=user)

        # Filters
        form = InvoiceFilterForm(self.request.GET)
        if form.is_valid():
            q = form.cleaned_data.get("q")
            status = form.cleaned_data.get("status")
            customer = form.cleaned_data.get("customer")
            date_from = form.cleaned_data.get("date_from")
            date_to = form.cleaned_data.get("date_to")
            overdue_only = form.cleaned_data.get("overdue_only")

            if q:
                qs = qs.filter(
                    Q(invoice_number__icontains=q)
                    | Q(customer__company_name__icontains=q)
                    | Q(customer__user__username__icontains=q)
                    | Q(customer__billing_email__icontains=q)
                )
            if status:
                qs = qs.filter(status=status)
            if customer and (getattr(user, "is_staff_role", False) or user.is_staff):
                qs = qs.filter(customer=customer)
            if date_from:
                qs = qs.filter(issue_date__gte=date_from)
            if date_to:
                qs = qs.filter(issue_date__lte=date_to)
            if overdue_only:
                today = timezone.now().date()
                qs = qs.filter(
                    status__in=[Invoice.Status.DRAFT, Invoice.Status.CONFIRMED],
                    due_date__lt=today,
                )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = InvoiceFilterForm(self.request.GET)
        context["is_staff_user"] = (
            getattr(self.request.user, "is_staff_role", False)
            or self.request.user.is_staff
            or self.request.user.is_superuser
        )
        return context


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = "invoicing/invoice_detail.html"
    context_object_name = "invoice"

    def get_queryset(self):
        return (
            Invoice.objects.select_related(
                "customer",
                "customer__user",
                "subscription",
                "subscription__plan",
            )
            .prefetch_related(
                "lines",
                "lines__product",
                "lines__tax",
                "tax_lines",
                "discount_usages",
                "discount_usages__discount",
                "payments",
            )
        )

    def get_object(self, queryset=None):
        invoice = super().get_object(queryset)
        user = self.request.user

        # Access check: customer can only view their own invoice
        is_staff_or_admin = (
            getattr(user, "is_staff_role", False) or user.is_staff or user.is_superuser
        )
        if not is_staff_or_admin:
            if invoice.customer.user != user:
                raise PermissionDenied("You do not have permission to view this invoice.")

        return invoice

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["can_manage"] = (
            getattr(user, "is_staff_role", False) or user.is_staff or user.is_superuser
        )
        return context


class InvoiceCreateView(StaffOrAdminRequiredMixin, FormView):
    """Manual invoice generation view for Staff and Admin."""
    template_name = "invoicing/invoice_generate.html"
    form_class = InvoiceGenerateForm

    def form_valid(self, form):
        subscription = form.cleaned_data["subscription"]
        period_start = form.cleaned_data["billing_period_start"]
        period_end = form.cleaned_data["billing_period_end"]

        try:
            invoice = InvoiceService.generate_for_subscription(
                subscription=subscription,
                period_start=period_start,
                period_end=period_end,
            )
            messages.success(
                self.request,
                f"Invoice {invoice.invoice_number} created successfully for {subscription.customer}.",
            )
            return redirect("invoicing:invoice_detail", pk=invoice.pk)
        except Exception as exc:
            messages.error(self.request, f"Failed to generate invoice: {exc}")
            return self.form_invalid(form)


class InvoiceConfirmView(StaffOrAdminRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        try:
            InvoiceService.confirm(invoice)
            messages.success(request, f"Invoice {invoice.invoice_number} has been confirmed.")
        except ValidationError as exc:
            messages.error(request, str(exc.message if hasattr(exc, "message") else exc))
        return redirect("invoicing:invoice_detail", pk=pk)


class InvoiceCancelView(StaffOrAdminRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        try:
            InvoiceService.cancel(invoice)
            messages.warning(request, f"Invoice {invoice.invoice_number} has been cancelled.")
        except ValidationError as exc:
            messages.error(request, str(exc.message if hasattr(exc, "message") else exc))
        return redirect("invoicing:invoice_detail", pk=pk)


class InvoiceSendView(StaffOrAdminRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        try:
            InvoiceService.send(invoice)
            messages.success(
                request,
                f"Invoice {invoice.invoice_number} successfully emailed to "
                f"{invoice.customer.billing_email or invoice.customer.user.email} with PDF attached.",
            )
        except Exception as exc:
            messages.error(request, f"Failed to send invoice email: {exc}")
        return redirect("invoicing:invoice_detail", pk=pk)


class InvoicePrintView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = "invoicing/invoice_print.html"
    context_object_name = "invoice"

    def get_object(self, queryset=None):
        invoice = super().get_object(queryset)
        user = self.request.user
        is_staff_or_admin = (
            getattr(user, "is_staff_role", False) or user.is_staff or user.is_superuser
        )
        if not is_staff_or_admin and invoice.customer.user != user:
            raise PermissionDenied("You do not have permission to view this invoice.")
        return invoice


class InvoicePDFView(LoginRequiredMixin, View):
    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        user = request.user
        is_staff_or_admin = (
            getattr(user, "is_staff_role", False) or user.is_staff or user.is_superuser
        )
        if not is_staff_or_admin and invoice.customer.user != user:
            raise PermissionDenied("You do not have permission to view this invoice.")

        try:
            pdf_bytes = InvoiceService.render_pdf(invoice)
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{invoice.invoice_number}.pdf"'
            return response
        except Exception as exc:
            messages.error(request, f"Could not generate PDF: {exc}")
            return redirect("invoicing:invoice_detail", pk=pk)


# --- Tax Configuration Views (ADMIN ONLY) ---

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
        messages.success(self.request, f"Tax rate '{form.cleaned_data['name']}' created successfully.")
        return super().form_valid(form)


class TaxUpdateView(AdminRequiredMixin, UpdateView):
    model = Tax
    form_class = TaxForm
    template_name = "invoicing/tax_form.html"
    success_url = reverse_lazy("invoicing:tax_list")

    def form_valid(self, form):
        messages.success(self.request, f"Tax rate '{form.cleaned_data['name']}' updated successfully.")
        return super().form_valid(form)

