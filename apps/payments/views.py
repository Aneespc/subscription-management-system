from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice, Payment
from .permissions import IsStaffOrAdmin
from .serializers import (InvoiceBalanceSerializer, OutstandingSerializer,
                          PaymentCreateSerializer, PaymentSerializer)
from .services import calculate_outstanding, get_overdue_invoices, get_payable_invoices


@extend_schema_view(
    list=extend_schema(
        summary="List payments",
        parameters=[
            OpenApiParameter("invoice", OpenApiTypes.INT, description="Only payments for this invoice id."),
            OpenApiParameter("method", OpenApiTypes.STR, enum=Payment.PaymentMethod.values),
            OpenApiParameter("date_from", OpenApiTypes.DATE, description="On or after (YYYY-MM-DD)."),
            OpenApiParameter("date_to", OpenApiTypes.DATE, description="On or before (YYYY-MM-DD)."),
        ],
    ),
    retrieve=extend_schema(summary="Get one payment"),
    create=extend_schema(
        summary="Record a payment against a CONFIRMED invoice",
        description="Rejects overpayments and payments on non-confirmed invoices. "
                    "The invoice becomes PAID when its balance reaches zero.",
        request=PaymentCreateSerializer,
        responses={201: PaymentSerializer},
    ),
)
class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsStaffOrAdmin]

    def get_serializer_class(self):
        return PaymentCreateSerializer if self.action == "create" else PaymentSerializer

    def get_queryset(self):
        qs = Payment.objects.select_related("invoice", "recorded_by").order_by("-payment_date", "-id")
        p = self.request.query_params
        if p.get("invoice"):
            qs = qs.filter(invoice_id=p["invoice"])
        if p.get("method"):
            qs = qs.filter(payment_method=p["method"])
        if p.get("date_from"):
            qs = qs.filter(payment_date__date__gte=p["date_from"])
        if p.get("date_to"):
            qs = qs.filter(payment_date__date__lte=p["date_to"])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


@extend_schema(summary="Payments recorded against one invoice")
class InvoicePaymentsView(generics.ListAPIView):
    permission_classes = [IsStaffOrAdmin]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payment.objects.none()
        invoice = get_object_or_404(Invoice, pk=self.kwargs["pk"])
        return invoice.payments.select_related("invoice", "recorded_by").order_by("-payment_date")


class InvoiceOutstandingView(APIView):
    permission_classes = [IsStaffOrAdmin]

    @extend_schema(summary="Outstanding balance of one invoice", responses=OutstandingSerializer)
    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        outstanding = calculate_outstanding(invoice)
        return Response({
            "invoice_number": invoice.invoice_number,
            "status": invoice.status,
            "total_amount": invoice.total_amount,
            "total_paid": invoice.total_amount - outstanding,
            "outstanding": outstanding,
        })


@extend_schema(summary="Overdue invoices (confirmed, past due date, balance left)")
class OverdueInvoicesView(generics.ListAPIView):
    permission_classes = [IsStaffOrAdmin]
    serializer_class = InvoiceBalanceSerializer

    def get_queryset(self):
        return get_overdue_invoices().order_by("due_date")


@extend_schema(
    summary="Invoices that can still receive a payment",
    parameters=[OpenApiParameter("search", OpenApiTypes.STR, description="Part of the invoice number.")],
)
class PayableInvoicesView(generics.ListAPIView):
    permission_classes = [IsStaffOrAdmin]
    serializer_class = InvoiceBalanceSerializer

    def get_queryset(self):
        qs = get_payable_invoices()
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(invoice_number__icontains=search)
        return qs.order_by("due_date", "id")