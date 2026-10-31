from django.contrib import admin
from django.urls import include, path

from apps.dashboard.views import dashboard_page

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.payments.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("dashboard/", dashboard_page, name="dashboard"),
    path("accounts/", include("accounts.urls")),
]

