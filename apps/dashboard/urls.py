from django.urls import path

from .views import DashboardPageView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardPageView.as_view(), name="index"),
]
