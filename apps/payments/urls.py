from django.urls import path

from . import gateway_views, views

app_name = "payments"

urlpatterns = [
    path("", views.PaymentListView.as_view(), name="list"),
    path("record/<int:invoice_pk>/", views.PaymentRecordView.as_view(), name="record"),
    path("razorpay/checkout/<int:invoice_pk>/", gateway_views.CheckoutView.as_view(), name="razorpay_checkout"),
    path("razorpay/callback/<int:order_pk>/", gateway_views.CallbackView.as_view(), name="razorpay_callback"),
    path("razorpay/webhook/", gateway_views.WebhookView.as_view(), name="razorpay_webhook"),
]
