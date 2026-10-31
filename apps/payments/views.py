from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice, Payment
from .permissions import IsStaffOrAdmin
from .serializers import OverdueInvoiceSerializer, PaymentCreateSerializer, PaymentSerializer
from .services import calculate_outstanding, get_overdue_invoices


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


class InvoicePaymentsView(generics.ListAPIView):
    permission_classes = [IsStaffOrAdmin]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        invoice = get_object_or_404(Invoice, pk=self.kwargs["pk"])
        return invoice.payments.select_related("invoice", "recorded_by").order_by("-payment_date")


class InvoiceOutstandingView(APIView):
    permission_classes = [IsStaffOrAdmin]

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


class OverdueInvoicesView(generics.ListAPIView):
    permission_classes = [IsStaffOrAdmin]
    serializer_class = OverdueInvoiceSerializer

    def get_queryset(self):
        return get_overdue_invoices().order_by("due_date")