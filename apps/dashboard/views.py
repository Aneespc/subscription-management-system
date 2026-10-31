from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.mixins import StaffRequiredMixin
from apps.payments.models import Payment
from apps.payments.services import get_overdue_invoices
from apps.subscriptions.models import Subscription

from . import services
from .services import DashboardFilterForm


class DashboardPageView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        form = DashboardFilterForm(self.request.GET or None)
        data = form.cleaned_data if form.is_valid() else {}
        method_labels = dict(Payment.PaymentMethod.choices)
        overdue = list(get_overdue_invoices().select_related("customer").order_by("due_date")[:25])
        for invoice in overdue:
            invoice.days_late = (today - invoice.due_date).days
        context.update(
            {
                "filter_form": form,
                "summary": services.get_summary(data),
                "payments_by_method": [
                    {**row, "label": method_labels.get(row["payment_method"], row["payment_method"])}
                    for row in services.payments_by_method(data)
                ],
                "payments": services.filter_payments(data).select_related("invoice", "invoice__customer").order_by("-payment_date")[:25],
                "active_subscriptions": services.filter_subscriptions(data)
                .filter(status=Subscription.Status.ACTIVE)
                .select_related("customer", "plan")
                .order_by("next_billing_date")[:25],
                "overdue_invoices": overdue,
                "today": today,
                "has_filters": bool(self.request.GET),
            }
        )
        return context
