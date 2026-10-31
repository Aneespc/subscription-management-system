from django.urls import path

from apps.invoicing import views

app_name = "invoicing"

urlpatterns = [
    path("", views.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/", views.InvoiceListView.as_view(), name="invoice_list_alt"),
    path("invoices/billing-run/", views.BillingRunView.as_view(), name="billing_run"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/confirm/", views.InvoiceConfirmView.as_view(), name="invoice_confirm"),
    path("invoices/<int:pk>/cancel/", views.InvoiceCancelView.as_view(), name="invoice_cancel"),
    path("invoices/<int:pk>/send/", views.InvoiceSendView.as_view(), name="invoice_send"),
    path("invoices/<int:pk>/print/", views.InvoicePrintView.as_view(), name="invoice_print"),
    path("invoices/<int:pk>/pdf/", views.InvoicePDFView.as_view(), name="invoice_pdf"),
    path("invoices/send-reminders/", views.SendRemindersView.as_view(), name="send_reminders"),
    path("taxes/", views.TaxListView.as_view(), name="tax_list"),
    path("taxes/create/", views.TaxCreateView.as_view(), name="tax_create"),
    path("taxes/<int:pk>/edit/", views.TaxUpdateView.as_view(), name="tax_edit"),
]
