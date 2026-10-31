from django.contrib import admin

from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("quotations/", include("apps.quotations.urls")),
    path("subscriptions/", include("apps.subscriptions.urls")),
    path("", lambda request: redirect("subscriptions:list"), name="home"),
    path("api/", include("apps.payments.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("dashboard/", dashboard_page, name="dashboard"),
]

