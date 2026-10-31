from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.shortcuts import render
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payments.models import Payment
from apps.payments.permissions import IsStaffOrAdmin
from apps.payments.serializers import InvoiceBalanceSerializer, PaymentSerializer
from apps.payments.services import get_overdue_invoices

from . import services
from .cache_utils import cache_key

CACHE_SECONDS = 30

FILTER_PARAMS = [
    OpenApiParameter("date_from", OpenApiTypes.DATE, description="Payments on or after (YYYY-MM-DD)."),
    OpenApiParameter("date_to", OpenApiTypes.DATE, description="Payments on or before (YYYY-MM-DD)."),
    OpenApiParameter("method", OpenApiTypes.STR, enum=Payment.PaymentMethod.values),
    OpenApiParameter("invoice_status", OpenApiTypes.STR, description="Status of the invoice the payment belongs to."),
    OpenApiParameter("group", OpenApiTypes.STR, enum=["month", "quarter", "year"], description="Revenue grouping."),
]


@staff_member_required
def dashboard_page(request):
    """The HTML dashboard. Redirects to the admin login if not logged in as staff."""
    return render(request, "dashboard/index.html")


class CachedDashboardView(APIView):
    permission_classes = [IsStaffOrAdmin]

    def build(self, params):
        raise NotImplementedError

    def get(self, request):
        key = cache_key(request.get_full_path())
        data = cache.get(key)
        if data is None:
            data = self.build(request.query_params)
            cache.set(key, data, CACHE_SECONDS)
        return Response(data)


@extend_schema(summary="Headline numbers", parameters=FILTER_PARAMS, responses=OpenApiTypes.OBJECT)
class SummaryView(CachedDashboardView):
    def build(self, params):
        return services.get_summary(params)


@extend_schema(summary="Revenue received per month, quarter or year",
               parameters=FILTER_PARAMS, responses=OpenApiTypes.OBJECT)
class RevenueView(CachedDashboardView):
    def build(self, params):
        return {"group": params.get("group", "month"), "results": services.revenue_by_period(params)}


@extend_schema(summary="Summary, revenue by period and payments by method in one response",
               parameters=FILTER_PARAMS, responses=OpenApiTypes.OBJECT)
class ReportsView(CachedDashboardView):
    def build(self, params):
        return services.get_report(params)


@extend_schema(summary="Overdue balances grouped by days past due", responses=OpenApiTypes.OBJECT)
class AgingView(CachedDashboardView):
    def build(self, params):
        return services.get_aging_report()


class SubscriptionsView(APIView):
    permission_classes = [IsStaffOrAdmin]

    @extend_schema(summary="Subscription distribution (pending Member 2's models)",
                   responses=OpenApiTypes.OBJECT)
    def get(self, request):
        # TODO: aggregate Subscription by status once Member 2's models land
        return Response({"detail": "Waiting for Subscription model.", "distribution": []})


@extend_schema(summary="Filtered payment list", parameters=FILTER_PARAMS)
class PaymentsListView(generics.ListAPIView):
    permission_classes = [IsStaffOrAdmin]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payment.objects.none()
        return services.filter_payments(self.request.query_params) \
            .select_related("invoice", "recorded_by").order_by("-payment_date")


@extend_schema(summary="Overdue invoices with balances")
class OverdueInvoicesView(generics.ListAPIView):
    permission_classes = [IsStaffOrAdmin]
    serializer_class = InvoiceBalanceSerializer

    def get_queryset(self):
        return get_overdue_invoices().order_by("due_date")