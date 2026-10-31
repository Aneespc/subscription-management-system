from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.shortcuts import render
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payments.permissions import IsStaffOrAdmin
from apps.payments.serializers import OverdueInvoiceSerializer, PaymentSerializer
from apps.payments.services import get_overdue_invoices

from . import services

CACHE_SECONDS = 30


@staff_member_required
def dashboard_page(request):
    """The HTML dashboard. Redirects to the admin login if not logged in as staff."""
    return render(request, "dashboard/index.html")


class CachedDashboardView(APIView):
    permission_classes = [IsStaffOrAdmin]

    def build(self, params):
        raise NotImplementedError

    def get(self, request):
        key = "dash:" + request.get_full_path()
        data = cache.get(key)
        if data is None:
            data = self.build(request.query_params)
            cache.set(key, data, CACHE_SECONDS)
        return Response(data)


class SummaryView(CachedDashboardView):
    def build(self, params):
        return services.get_summary(params)


class RevenueView(CachedDashboardView):
    def build(self, params):
        return {"group": params.get("group", "month"), "results": services.revenue_by_period(params)}


class ReportsView(CachedDashboardView):
    def build(self, params):
        return services.get_report(params)


class SubscriptionsView(APIView):
    permission_classes = [IsStaffOrAdmin]

    def get(self, request):
        # TODO: aggregate Subscription by status once Member 2's models land
        return Response({"detail": "Waiting for Subscription model.", "distribution": []})


class PaymentsListView(generics.ListAPIView):
    permission_classes = [IsStaffOrAdmin]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        return services.filter_payments(self.request.query_params) \
            .select_related("invoice", "recorded_by").order_by("-payment_date")


class OverdueInvoicesView(generics.ListAPIView):
    permission_classes = [IsStaffOrAdmin]
    serializer_class = OverdueInvoiceSerializer

    def get_queryset(self):
        return get_overdue_invoices().order_by("due_date")