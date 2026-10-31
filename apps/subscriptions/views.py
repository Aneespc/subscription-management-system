from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView, DetailView
from django.contrib import messages
from django.urls import reverse
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from .models import Subscription, SubscriptionLine
from .forms import SubscriptionForm, SubscriptionLineFormSet, SubscriptionRenewForm
from .services import SubscriptionService
from apps.plans.models import Plan
from apps.accounts.models import CustomerProfile


class SubscriptionListView(ListView):
    model = Subscription
    template_name = "subscriptions/subscription_list.html"
    context_object_name = "subscriptions"
    paginate_by = 15

    def get_queryset(self):
        qs = Subscription.objects.select_related("customer", "plan", "quotation").all().order_by("-created_at")
        user = self.request.user
        if user.is_authenticated and hasattr(user, "role") and user.role == "CUSTOMER":
            qs = qs.filter(customer__user=user)

        status = self.request.GET.get("status")
        plan_id = self.request.GET.get("plan")
        customer_id = self.request.GET.get("customer")
        q = self.request.GET.get("q")

        if status:
            qs = qs.filter(status=status)
        if plan_id:
            qs = qs.filter(plan_id=plan_id)
        if customer_id and (not user.is_authenticated or user.role != "CUSTOMER"):
            qs = qs.filter(customer_id=customer_id)
        if q:
            qs = qs.filter(
                Q(subscription_number__icontains=q) |
                Q(customer__company_name__icontains=q) |
                Q(customer__user__email__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_authenticated and hasattr(user, "role") and user.role == "CUSTOMER":
            all_subs = Subscription.objects.filter(customer__user=user)
        else:
            all_subs = Subscription.objects.all()
        today = timezone.now().date()
        expiring_soon_date = today + timedelta(days=14)

        context["kpis"] = {
            "total": all_subs.count(),
            "active": all_subs.filter(status=Subscription.Status.ACTIVE).count(),
            "confirmed": all_subs.filter(status=Subscription.Status.CONFIRMED).count(),
            "paused": all_subs.filter(status=Subscription.Status.PAUSED).count(),
            "closed": all_subs.filter(status=Subscription.Status.CLOSED).count(),
            "expiring_soon": all_subs.filter(
                status=Subscription.Status.ACTIVE,
                expiry_date__lte=expiring_soon_date,
                expiry_date__gte=today
            ).count()
        }
        context["plans"] = Plan.objects.filter(is_active=True)
        context["customers"] = CustomerProfile.objects.all()
        context["current_status"] = self.request.GET.get("status", "")
        context["selected_plan"] = self.request.GET.get("plan", "")
        context["selected_customer"] = self.request.GET.get("customer", "")
        context["search_query"] = self.request.GET.get("q", "")
        return context


class SubscriptionDetailView(DetailView):
    model = Subscription
    template_name = "subscriptions/subscription_detail.html"
    context_object_name = "subscription"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("product", "variant").all()
        context["renew_form"] = SubscriptionRenewForm()
        return context


class SubscriptionCreateView(View):
    template_name = "subscriptions/subscription_form.html"

    def get(self, request):
        form = SubscriptionForm()
        formset = SubscriptionLineFormSet()
        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "title": "Create Subscription"
        })

    def post(self, request):
        form = SubscriptionForm(request.POST)
        formset = SubscriptionLineFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            subscription = form.save()
            formset.instance = subscription
            formset.save()
            messages.success(request, f"Subscription {subscription.subscription_number} created successfully!")
            return redirect("subscriptions:detail", pk=subscription.pk)

        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "title": "Create Subscription"
        })


class SubscriptionUpdateView(View):
    template_name = "subscriptions/subscription_form.html"

    def get(self, request, pk):
        subscription = get_object_or_404(Subscription, pk=pk)
        form = SubscriptionForm(instance=subscription)
        formset = SubscriptionLineFormSet(instance=subscription)
        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "subscription": subscription,
            "title": f"Edit Subscription {subscription.subscription_number}"
        })

    def post(self, request, pk):
        subscription = get_object_or_404(Subscription, pk=pk)
        form = SubscriptionForm(request.POST, instance=subscription)
        formset = SubscriptionLineFormSet(request.POST, instance=subscription)

        if form.is_valid() and formset.is_valid():
            subscription = form.save()
            formset.save()
            messages.success(request, f"Subscription {subscription.subscription_number} updated.")
            return redirect("subscriptions:detail", pk=subscription.pk)

        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "subscription": subscription,
            "title": f"Edit Subscription {subscription.subscription_number}"
        })


class SubscriptionActionView(View):
    def post(self, request, pk, action):
        subscription = get_object_or_404(Subscription, pk=pk)
        service = SubscriptionService()

        try:
            if action == "activate":
                service.activate(subscription)
                messages.success(request, f"Subscription {subscription.subscription_number} is now ACTIVE.")
            elif action == "pause":
                service.pause(subscription)
                messages.warning(request, f"Subscription {subscription.subscription_number} is now PAUSED.")
            elif action == "resume":
                service.resume(subscription)
                messages.success(request, f"Subscription {subscription.subscription_number} has been RESUMED.")
            elif action == "renew":
                days_input = request.POST.get("additional_days")
                days = int(days_input) if days_input and days_input.isdigit() else None
                service.renew(subscription, additional_days=days)
                messages.success(
                    request,
                    f"Subscription {subscription.subscription_number} renewed until {subscription.expiry_date}."
                )
            elif action == "close":
                service.close(subscription)
                messages.info(request, f"Subscription {subscription.subscription_number} is now CLOSED.")
            else:
                messages.error(request, "Invalid action requested.")
        except ValueError as err:
            messages.error(request, str(err))
        except Exception as e:
            messages.error(request, f"Error performing action: {str(e)}")

        return redirect("subscriptions:detail", pk=subscription.pk)


class SelectPlanView(View):
    """Catalog where customers or staff can view plans and initiate a subscription or quotation."""
    template_name = "subscriptions/select_plan.html"

    def get(self, request):
        plans = Plan.objects.filter(is_active=True).order_by("price")
        customers = CustomerProfile.objects.all()
        return render(request, self.template_name, {
            "plans": plans,
            "customers": customers
        })
