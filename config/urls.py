from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("discounts/", include("apps.discounts.urls", namespace="discounts")),
    path("invoicing/", include("apps.invoicing.urls", namespace="invoicing")),
    path("", RedirectView.as_view(url="/invoicing/invoices/", permanent=False)),
]

