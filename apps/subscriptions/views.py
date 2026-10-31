from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts.mixins import StaffRequiredMixin, is_staff_user
from apps.accounts.models import CustomerProfile
from apps.plans.models import Plan
from apps.products.models import ProductVariant

from .forms import CheckoutLineFormSet, SubscriptionForm, SubscriptionLineFormSet
from .models import Subscription
from .services import SubscriptionService

CUSTOMER_ACTIONS = {"pause", "resume", "renew", "close"}


def scoped_subscriptions(user):
    qs = Subscription.objects.all()
    if not is_staff_user(user):
        qs = qs.filter(customer__user=user)
    return qs


class SubscriptionListView(LoginRequiredMixin, ListView):
    template_name = "subscriptions/subscription_list.html"
    context_object_name = "subscriptions"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            scoped_subscriptions(self.request.user)
            .select_related("customer", "customer__user", "plan", "quotation")
            .annotate(lines_total=Sum("lines__amount"), lines_quantity=Sum("lines__quantity"))
            .order_by("-created_at")
        )
        params = self.request.GET
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("plan"):
            qs = qs.filter(plan_id=params["plan"])
        if params.get("customer") and is_staff_user(self.request.user):
            qs = qs.filter(customer_id=params["customer"])
        if params.get("q"):
            q = params["q"]
            qs = qs.filter(
                Q(subscription_number__icontains=q)
                | Q(customer__company_name__icontains=q)
                | Q(customer__user__email__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = scoped_subscriptions(self.request.user)
        today = timezone.localdate()
        counts = base.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(status="ACTIVE")),
            confirmed=Count("id", filter=Q(status="CONFIRMED")),
            paused=Count("id", filter=Q(status="PAUSED")),
            closed=Count("id", filter=Q(status="CLOSED")),
            draft=Count("id", filter=Q(status__in=["DRAFT", "QUOTATION"])),
            expiring_soon=Count(
                "id",
                filter=Q(status="ACTIVE", expiry_date__gte=today, expiry_date__lte=today + timedelta(days=14)),
            ),
        )
        context["kpis"] = counts
        context["plans"] = Plan.objects.filter(is_active=True)
        context["customers"] = CustomerProfile.objects.order_by("company_name") if is_staff_user(self.request.user) else []
        context["is_staff_user"] = is_staff_user(self.request.user)
        context["current_status"] = self.request.GET.get("status", "")
        context["selected_plan"] = self.request.GET.get("plan", "")
        context["selected_customer"] = self.request.GET.get("customer", "")
        context["search_query"] = self.request.GET.get("q", "")
        context["statuses"] = Subscription.Status.choices
        return context


class SubscriptionDetailView(LoginRequiredMixin, DetailView):
    template_name = "subscriptions/subscription_detail.html"
    context_object_name = "subscription"

    def get_queryset(self):
        return scoped_subscriptions(self.request.user).select_related(
            "customer", "customer__user", "plan", "quotation"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("product", "variant")
        context["invoices"] = self.object.invoices.order_by("-issue_date", "-id")[:10]
        context["is_staff_user"] = is_staff_user(self.request.user)
        return context


class SubscriptionFormView(StaffRequiredMixin, View):
    template_name = "subscriptions/subscription_form.html"

    def get_subscription(self, pk):
        return get_object_or_404(Subscription, pk=pk) if pk else None

    def render_form(self, request, form, formset, subscription):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "formset": formset,
                "subscription": subscription,
                "title": f"Edit {subscription.subscription_number}" if subscription else "New Subscription",
                "variant_map": {str(v["id"]): str(v["product_id"]) for v in ProductVariant.objects.values("id", "product_id")},
            },
        )

    def get(self, request, pk=None):
        subscription = self.get_subscription(pk)
        return self.render_form(
            request,
            SubscriptionForm(instance=subscription),
            SubscriptionLineFormSet(instance=subscription),
            subscription,
        )

    def post(self, request, pk=None):
        subscription = self.get_subscription(pk)
        form = SubscriptionForm(request.POST, instance=subscription)
        formset = SubscriptionLineFormSet(request.POST, instance=subscription)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                subscription = form.save()
                formset.instance = subscription
                formset.save()
                if subscription.status == Subscription.Status.ACTIVE and not subscription.next_billing_date:
                    subscription.next_billing_date = subscription.calculate_next_billing_date(subscription.start_date)
                    subscription.save(update_fields=["next_billing_date"])
            messages.success(request, f"Subscription {subscription.subscription_number} saved.")
            return redirect("subscriptions:detail", pk=subscription.pk)
        return self.render_form(request, form, formset, subscription)


class SubscriptionActionView(LoginRequiredMixin, View):
    def post(self, request, pk, action):
        subscription = get_object_or_404(
            scoped_subscriptions(request.user).select_related("plan", "customer"), pk=pk
        )
        if not is_staff_user(request.user) and action not in CUSTOMER_ACTIONS:
            raise PermissionDenied("Customers cannot perform this action.")
        service = SubscriptionService()
        number = subscription.subscription_number
        try:
            if action == "confirm":
                service.confirm(subscription)
                messages.success(request, f"{number} confirmed.")
            elif action == "activate":
                service.activate(subscription)
                messages.success(request, f"{number} is now active. Next billing on {subscription.next_billing_date:%b %d, %Y}.")
            elif action == "pause":
                service.pause(subscription)
                messages.warning(request, f"{number} has been paused.")
            elif action == "resume":
                service.resume(subscription)
                messages.success(request, f"{number} has been resumed.")
            elif action == "renew":
                days = request.POST.get("additional_days", "").strip()
                service.renew(subscription, additional_days=int(days) if days.isdigit() else None)
                messages.success(request, f"{number} renewed until {subscription.expiry_date:%b %d, %Y}.")
            elif action == "close":
                service.close(subscription, force=is_staff_user(request.user) and request.POST.get("force") == "1")
                messages.info(request, f"{number} has been closed.")
            else:
                messages.error(request, "Unknown action.")
        except ValueError as err:
            messages.error(request, str(err))
        return redirect("subscriptions:detail", pk=subscription.pk)



class PlanCatalogView(LoginRequiredMixin, View):
    template_name = "subscriptions/plan_catalog.html"

    def get(self, request):
        plans = [p for p in Plan.objects.filter(is_active=True).order_by("price") if p.is_available]
        featured = max(plans, key=lambda p: p.price, default=None)
        return render(request, self.template_name, {"plans": plans, "featured": featured, "is_staff_user": is_staff_user(request.user)})


class SubscribeView(LoginRequiredMixin, View):
    template_name = "subscriptions/subscribe.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and is_staff_user(request.user):
            return redirect("subscriptions:create")
        return super().dispatch(request, *args, **kwargs)

    def get_plan(self, pk):
        plan = get_object_or_404(Plan, pk=pk, is_active=True)
        if not plan.is_available:
            raise PermissionDenied("This plan is not available right now.")
        return plan

    def render_form(self, request, plan, formset):
        return render(
            request,
            self.template_name,
            {
                "plan": plan,
                "formset": formset,
                "variant_map": {str(v["id"]): str(v["product_id"]) for v in ProductVariant.objects.values("id", "product_id")},
                "terms": Subscription.PaymentTerms.choices,
            },
        )

    def get(self, request, pk):
        return self.render_form(request, self.get_plan(pk), CheckoutLineFormSet())

    def post(self, request, pk):
        plan = self.get_plan(pk)
        formset = CheckoutLineFormSet(request.POST)
        if formset.is_valid():
            quantity = sum(f.cleaned_data["quantity"] for f in formset.forms if f.cleaned_data and not f.cleaned_data.get("DELETE"))
            if quantity < plan.minimum_quantity:
                messages.error(request, f"{plan.name} needs at least {plan.minimum_quantity} unit(s). You selected {quantity}.")
                return self.render_form(request, plan, formset)
            customer, _ = CustomerProfile.objects.get_or_create(user=request.user, defaults={"company_name": request.user.email})
            terms = request.POST.get("payment_terms", Subscription.PaymentTerms.NET_30)
            if terms not in Subscription.PaymentTerms.values:
                terms = Subscription.PaymentTerms.NET_30
            try:
                subscription, invoice = SubscriptionService().subscribe(customer, plan, formset, payment_terms=terms)
            except ValueError as err:
                messages.error(request, str(err))
                return self.render_form(request, plan, formset)
            messages.success(request, f"You are subscribed to {plan.name}. Your first invoice {invoice.invoice_number} is ready.")
            return redirect("invoicing:invoice_detail", pk=invoice.pk)
        return self.render_form(request, plan, formset)
