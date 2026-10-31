from django.urls import path

from .views import (AgingView, OverdueInvoicesView, PaymentsListView, ReportsView,
                    RevenueView, SubscriptionsView, SummaryView)

urlpatterns = [
    path("summary/", SummaryView.as_view()),
    path("revenue/", RevenueView.as_view()),
    path("subscriptions/", SubscriptionsView.as_view()),
    path("payments/", PaymentsListView.as_view()),
    path("overdue-invoices/", OverdueInvoicesView.as_view()),
    path("aging/", AgingView.as_view()),
    path("reports/", ReportsView.as_view()),
]