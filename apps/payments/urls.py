from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (InvoiceOutstandingView, InvoicePaymentsView, OverdueInvoicesView,
                    PayableInvoicesView, PaymentViewSet)

router = DefaultRouter()
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = [
    path("invoices/overdue/", OverdueInvoicesView.as_view()),
    path("invoices/payable/", PayableInvoicesView.as_view()),
    path("invoices/<int:pk>/payments/", InvoicePaymentsView.as_view()),
    path("invoices/<int:pk>/outstanding/", InvoiceOutstandingView.as_view()),
] + router.urls