from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts.mixins import StaffRequiredMixin
from apps.accounts.models import CustomerProfile
from apps.products.models import ProductVariant

from .forms import (
    QuotationForm,
    QuotationLineFormSet,
    QuotationTemplateForm,
    QuotationTemplateLineFormSet,
    TemplateSelectForm,
)
from .models import Quotation, QuotationTemplate
from .services import QuotationService


class QuotationListView(StaffRequiredMixin, ListView):
    template_name = "quotations/quotation_list.html"
    context_object_name = "quotations"
    paginate_by = 20

    def get_queryset(self):
        qs = Quotation.objects.select_related("customer", "customer__user", "template", "plan", "created_by")
        params = self.request.GET
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("customer"):
            qs = qs.filter(customer_id=params["customer"])
        if params.get("q"):
            q = params["q"]
            qs = qs.filter(
                Q(quotation_number__icontains=q)
                | Q(customer__company_name__icontains=q)
                | Q(customer__user__email__icontains=q)
            )
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_counts"] = Quotation.objects.aggregate(
            all=Count("id"),
            draft=Count("id", filter=Q(status="DRAFT")),
            quotation=Count("id", filter=Q(status="QUOTATION")),
            confirmed=Count("id", filter=Q(status="CONFIRMED")),
            converted=Count("id", filter=Q(status="CONVERTED")),
        )
        context["customers"] = CustomerProfile.objects.order_by("company_name")
        context["current_status"] = self.request.GET.get("status", "")
        context["search_query"] = self.request.GET.get("q", "")
        context["selected_customer"] = self.request.GET.get("customer", "")
        return context


class QuotationDetailView(StaffRequiredMixin, DetailView):
    template_name = "quotations/quotation_detail.html"
    context_object_name = "quotation"

    def get_queryset(self):
        return Quotation.objects.select_related("customer", "customer__user", "template", "plan", "created_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("product", "variant")
        return context


class QuotationPrintView(QuotationDetailView):
    template_name = "quotations/quotation_print.html"


class QuotationFormView(StaffRequiredMixin, View):
    template_name = "quotations/quotation_form.html"

    def get_quotation(self, pk):
        if not pk:
            return None
        quotation = get_object_or_404(Quotation, pk=pk)
        if not quotation.can_edit():
            raise PermissionDenied("Only draft or sent quotations can be edited.")
        return quotation

    def render_form(self, request, form, formset, quotation):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "formset": formset,
                "quotation": quotation,
                "title": f"Edit {quotation.quotation_number}" if quotation else "New Quotation",
                "variant_map": {str(v["id"]): str(v["product_id"]) for v in ProductVariant.objects.values("id", "product_id")},
            },
        )

    def get(self, request, pk=None):
        quotation = self.get_quotation(pk)
        return self.render_form(
            request, QuotationForm(instance=quotation), QuotationLineFormSet(instance=quotation), quotation
        )

    def post(self, request, pk=None):
        quotation = self.get_quotation(pk)
        form = QuotationForm(request.POST, instance=quotation)
        formset = QuotationLineFormSet(request.POST, instance=quotation)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                quotation = form.save(commit=False)
                if not quotation.pk:
                    quotation.created_by = request.user
                quotation.save()
                formset.instance = quotation
                formset.save()
                QuotationService.recalculate_totals(quotation)
            messages.success(request, f"Quotation {quotation.quotation_number} saved.")
            return redirect("quotations:detail", pk=quotation.pk)
        return self.render_form(request, form, formset, quotation)


class QuotationActionView(StaffRequiredMixin, View):
    def post(self, request, pk, action):
        quotation = get_object_or_404(Quotation, pk=pk)
        number = quotation.quotation_number
        try:
            if action == "send":
                QuotationService.send_quotation(quotation)
                messages.success(request, f"{number} marked as sent to {quotation.customer.company_name}.")
            elif action == "confirm":
                QuotationService.confirm_quotation(quotation)
                messages.success(request, f"{number} confirmed.")
            elif action == "convert":
                subscription = QuotationService.convert_to_subscription(quotation)
                messages.success(request, f"{number} converted into subscription {subscription.subscription_number}.")
                return redirect("subscriptions:detail", pk=subscription.pk)
            else:
                messages.error(request, "Unknown action.")
        except ValueError as err:
            messages.error(request, str(err))
        return redirect("quotations:detail", pk=quotation.pk)


class CreateFromTemplateView(StaffRequiredMixin, View):
    template_name = "quotations/template_select.html"

    def render_page(self, request, form):
        templates = (
            QuotationTemplate.objects.filter(is_active=True)
            .select_related("plan")
            .prefetch_related("template_lines__product", "template_lines__variant")
        )
        return render(request, self.template_name, {"form": form, "templates": templates})

    def get(self, request):
        form = TemplateSelectForm(initial={"template": request.GET.get("template")})
        return self.render_page(request, form)

    def post(self, request):
        form = TemplateSelectForm(request.POST)
        if form.is_valid():
            quotation = QuotationService.create_from_template(
                template=form.cleaned_data["template"],
                customer=form.cleaned_data["customer"],
                created_by=request.user,
                payment_terms=form.cleaned_data["payment_terms"],
            )
            messages.success(request, f"Quotation {quotation.quotation_number} created from template.")
            return redirect("quotations:detail", pk=quotation.pk)
        return self.render_page(request, form)


class TemplateListView(StaffRequiredMixin, ListView):
    template_name = "quotations/template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        return (
            QuotationTemplate.objects.select_related("plan", "created_by")
            .prefetch_related("template_lines__product", "template_lines__variant")
            .annotate(quotation_count=Count("quotations"))
            .order_by("-is_active", "name")
        )


class TemplateFormView(StaffRequiredMixin, View):
    template_name = "quotations/template_form.html"

    def get_template(self, pk):
        return get_object_or_404(QuotationTemplate, pk=pk) if pk else None

    def render_form(self, request, form, formset, template):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "formset": formset,
                "template_obj": template,
                "title": f"Edit {template.name}" if template else "New Quotation Template",
                "variant_map": {str(v["id"]): str(v["product_id"]) for v in ProductVariant.objects.values("id", "product_id")},
            },
        )

    def get(self, request, pk=None):
        template = self.get_template(pk)
        return self.render_form(
            request, QuotationTemplateForm(instance=template), QuotationTemplateLineFormSet(instance=template), template
        )

    def post(self, request, pk=None):
        template = self.get_template(pk)
        form = QuotationTemplateForm(request.POST, instance=template)
        formset = QuotationTemplateLineFormSet(request.POST, instance=template)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                template = form.save(commit=False)
                if not template.pk:
                    template.created_by = request.user
                template.save()
                formset.instance = template
                formset.save()
            messages.success(request, f"Template {template.name} saved.")
            return redirect("quotations:template_list")
        return self.render_form(request, form, formset, template)
