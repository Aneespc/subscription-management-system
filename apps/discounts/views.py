from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.discounts.forms import DiscountFilterForm, DiscountForm
from apps.discounts.models import Discount
from apps.accounts.mixins import AdminRequiredMixin


class DiscountListView(AdminRequiredMixin, ListView):
    model = Discount
    template_name = "discounts/discount_list.html"
    context_object_name = "discounts"
    paginate_by = 20

    def get_queryset(self):
        qs = Discount.objects.prefetch_related("products").order_by("-created_at")
        form = DiscountFilterForm(self.request.GET)
        if form.is_valid():
            q = form.cleaned_data.get("q")
            discount_type = form.cleaned_data.get("discount_type")
            is_active = form.cleaned_data.get("is_active")

            if q:
                qs = qs.filter(name__icontains=q)
            if discount_type:
                qs = qs.filter(discount_type=discount_type)
            if is_active == "true":
                qs = qs.filter(is_active=True)
            elif is_active == "false":
                qs = qs.filter(is_active=False)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = DiscountFilterForm(self.request.GET)
        return context


class DiscountCreateView(AdminRequiredMixin, CreateView):
    model = Discount
    form_class = DiscountForm
    template_name = "discounts/discount_form.html"
    success_url = reverse_lazy("discounts:discount_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, f"Discount '{form.cleaned_data['name']}' created successfully.")
        return super().form_valid(form)


class DiscountUpdateView(AdminRequiredMixin, UpdateView):
    model = Discount
    form_class = DiscountForm
    template_name = "discounts/discount_form.html"
    success_url = reverse_lazy("discounts:discount_list")

    def form_valid(self, form):
        messages.success(self.request, f"Discount '{form.cleaned_data['name']}' updated successfully.")
        return super().form_valid(form)

