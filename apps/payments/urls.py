from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("", views.PaymentListView.as_view(), name="list"),
    path("record/<int:invoice_pk>/", views.PaymentRecordView.as_view(), name="record"),
]
