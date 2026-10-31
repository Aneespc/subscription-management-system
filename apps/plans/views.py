from django.contrib import messages
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.mixins import AdminRequiredMixin

from .forms import PlanForm
from .models import Plan


class PlanListView(AdminRequiredMixin, ListView):
    template_name = "plans/plan_list.html"
    context_object_name = "plans"
    paginate_by = 25

    def get_queryset(self):
        qs = Plan.objects.annotate(
            subscription_count=Count("subscriptions", distinct=True),
            active_count=Count("subscriptions", filter=Q(subscriptions__status="ACTIVE"), distinct=True),
        ).order_by("price", "name")
        q = self.request.GET.get("q", "").strip()
        interval = self.request.GET.get("interval", "")
        if q:
            qs = qs.filter(name__icontains=q)
        if interval:
            qs = qs.filter(billing_interval=interval)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        context["selected_interval"] = self.request.GET.get("interval", "")
        context["intervals"] = Plan.BillingInterval.choices
        return context


class PlanCreateView(AdminRequiredMixin, CreateView):
    model = Plan
    form_class = PlanForm
    template_name = "plans/plan_form.html"
    success_url = reverse_lazy("plans:list")

    def form_valid(self, form):
        messages.success(self.request, f"Plan {form.cleaned_data['name']} created.")
        return super().form_valid(form)


class PlanUpdateView(AdminRequiredMixin, UpdateView):
    model = Plan
    form_class = PlanForm
    template_name = "plans/plan_form.html"
    success_url = reverse_lazy("plans:list")

    def form_valid(self, form):
        messages.success(self.request, f"Plan {form.cleaned_data['name']} updated.")
        return super().form_valid(form)
