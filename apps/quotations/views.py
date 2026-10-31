from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Count
from .models import Quotation, QuotationLine, QuotationTemplate, QuotationTemplateLine
from .forms import (
    QuotationForm, QuotationLineFormSet,
    QuotationTemplateForm, QuotationTemplateLineFormSet,
    TemplateSelectForm
)
from .services import QuotationService
from apps.accounts.models import CustomerProfile


class QuotationListView(ListView):
    model = Quotation
    template_name = "quotations/quotation_list.html"
    context_object_name = "quotations"
    paginate_by = 15

    def get_queryset(self):
        qs = Quotation.objects.select_related("customer", "template", "created_by").all().order_by("-created_at")
        user = self.request.user
        if user.is_authenticated and hasattr(user, "role") and user.role == "CUSTOMER":
            qs = qs.filter(customer__user=user)

        status = self.request.GET.get("status")
        q = self.request.GET.get("q")
        customer_id = self.request.GET.get("customer")

        if status:
            qs = qs.filter(status=status)
        if customer_id and (not user.is_authenticated or user.role != "CUSTOMER"):
            qs = qs.filter(customer_id=customer_id)
        if q:
            qs = qs.filter(
                Q(quotation_number__icontains=q) |
                Q(customer__company_name__icontains=q) |
                Q(customer__user__email__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_authenticated and hasattr(user, "role") and user.role == "CUSTOMER":
            all_quotes = Quotation.objects.filter(customer__user=user)
        else:
            all_quotes = Quotation.objects.all()
        context["status_counts"] = {
            "all": all_quotes.count(),
            "draft": all_quotes.filter(status=Quotation.Status.DRAFT).count(),
            "quotation": all_quotes.filter(status=Quotation.Status.QUOTATION).count(),
            "confirmed": all_quotes.filter(status=Quotation.Status.CONFIRMED).count(),
            "converted": all_quotes.filter(status=Quotation.Status.CONVERTED).count(),
        }
        context["customers"] = CustomerProfile.objects.all()
        context["current_status"] = self.request.GET.get("status", "")
        context["search_query"] = self.request.GET.get("q", "")
        context["selected_customer"] = self.request.GET.get("customer", "")
        return context


class QuotationDetailView(DetailView):
    model = Quotation
    template_name = "quotations/quotation_detail.html"
    context_object_name = "quotation"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("product", "variant").all()
        return context


class QuotationPrintView(DetailView):
    model = Quotation
    template_name = "quotations/quotation_print.html"
    context_object_name = "quotation"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("product", "variant").all()
        return context


class QuotationCreateView(View):
    template_name = "quotations/quotation_form.html"

    def get(self, request):
        form = QuotationForm()
        formset = QuotationLineFormSet()
        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "title": "Create Quotation"
        })

    def post(self, request):
        form = QuotationForm(request.POST)
        formset = QuotationLineFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            quotation = form.save(commit=False)
            if request.user.is_authenticated:
                quotation.created_by = request.user
            quotation.save()

            formset.instance = quotation
            formset.save()

            QuotationService.recalculate_totals(quotation)
            messages.success(request, f"Quotation {quotation.quotation_number} created successfully!")
            return redirect("quotations:detail", pk=quotation.pk)

        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "title": "Create Quotation"
        })


class QuotationUpdateView(View):
    template_name = "quotations/quotation_form.html"

    def get(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk)
        form = QuotationForm(instance=quotation)
        formset = QuotationLineFormSet(instance=quotation)
        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "quotation": quotation,
            "title": f"Edit Quotation {quotation.quotation_number}"
        })

    def post(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk)
        form = QuotationForm(request.POST, instance=quotation)
        formset = QuotationLineFormSet(request.POST, instance=quotation)

        if form.is_valid() and formset.is_valid():
            quotation = form.save()
            formset.save()
            QuotationService.recalculate_totals(quotation)
            messages.success(request, f"Quotation {quotation.quotation_number} updated.")
            return redirect("quotations:detail", pk=quotation.pk)

        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "quotation": quotation,
            "title": f"Edit Quotation {quotation.quotation_number}"
        })


class QuotationActionView(View):
    def post(self, request, pk, action):
        quotation = get_object_or_404(Quotation, pk=pk)

        try:
            if action == "send":
                QuotationService.send_quotation(quotation)
                messages.success(request, f"Quotation {quotation.quotation_number} sent to customer.")
            elif action == "confirm":
                QuotationService.confirm_quotation(quotation)
                messages.success(request, f"Quotation {quotation.quotation_number} confirmed.")
            elif action == "convert":
                subscription = QuotationService.convert_to_subscription(quotation)
                messages.success(
                    request,
                    f"Quotation converted to Subscription {subscription.subscription_number}!"
                )
                return redirect("subscriptions:detail", pk=subscription.pk)
            elif action == "cancel":
                quotation.status = Quotation.Status.CANCELLED
                quotation.save(update_fields=["status"])
                messages.warning(request, f"Quotation {quotation.quotation_number} cancelled.")
            else:
                messages.error(request, "Unknown action.")
        except Exception as e:
            messages.error(request, f"Error processing action: {str(e)}")

        return redirect("quotations:detail", pk=quotation.pk)


class CreateFromTemplateView(View):
    template_name = "quotations/template_select.html"

    def get(self, request):
        form = TemplateSelectForm()
        templates = QuotationTemplate.objects.filter(is_active=True).select_related("plan")
        return render(request, self.template_name, {
            "form": form,
            "templates": templates
        })

    def post(self, request):
        form = TemplateSelectForm(request.POST)
        if form.is_valid():
            template = form.cleaned_data["template"]
            customer = form.cleaned_data["customer"]
            terms = form.cleaned_data["payment_terms"]
            created_by = request.user if request.user.is_authenticated else None

            quotation = QuotationService.create_from_template(
                template=template,
                customer=customer,
                created_by=created_by,
                payment_terms=terms
            )
            messages.success(
                request,
                f"Quotation {quotation.quotation_number} created from template '{template.name}'!"
            )
            return redirect("quotations:detail", pk=quotation.pk)

        templates = QuotationTemplate.objects.filter(is_active=True).select_related("plan")
        return render(request, self.template_name, {
            "form": form,
            "templates": templates
        })


class TemplateListView(ListView):
    model = QuotationTemplate
    template_name = "quotations/template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        return QuotationTemplate.objects.select_related("plan", "created_by").prefetch_related("template_lines").all()


class TemplateCreateView(View):
    template_name = "quotations/template_form.html"

    def get(self, request):
        form = QuotationTemplateForm()
        formset = QuotationTemplateLineFormSet()
        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "title": "Create Quotation Template"
        })

    def post(self, request):
        form = QuotationTemplateForm(request.POST)
        formset = QuotationTemplateLineFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            template = form.save(commit=False)
            if request.user.is_authenticated:
                template.created_by = request.user
            template.save()

            formset.instance = template
            formset.save()

            messages.success(request, f"Template '{template.name}' created successfully.")
            return redirect("quotations:template_list")

        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "title": "Create Quotation Template"
        })


class TemplateUpdateView(View):
    template_name = "quotations/template_form.html"

    def get(self, request, pk):
        template = get_object_or_404(QuotationTemplate, pk=pk)
        form = QuotationTemplateForm(instance=template)
        formset = QuotationTemplateLineFormSet(instance=template)
        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "template_obj": template,
            "title": f"Edit Template '{template.name}'"
        })

    def post(self, request, pk):
        template = get_object_or_404(QuotationTemplate, pk=pk)
        form = QuotationTemplateForm(request.POST, instance=template)
        formset = QuotationTemplateLineFormSet(request.POST, instance=template)

        if form.is_valid() and formset.is_valid():
            template = form.save()
            formset.save()
            messages.success(request, f"Template '{template.name}' updated.")
            return redirect("quotations:template_list")

        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "template_obj": template,
            "title": f"Edit Template '{template.name}'"
        })
