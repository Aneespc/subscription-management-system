from django.urls import include, path

from apps.accounts.views import HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("products/", include("apps.products.urls", namespace="products")),
    path("plans/", include("apps.plans.urls", namespace="plans")),
    path("quotations/", include("apps.quotations.urls", namespace="quotations")),
    path("subscriptions/", include("apps.subscriptions.urls", namespace="subscriptions")),
    path("discounts/", include("apps.discounts.urls", namespace="discounts")),
    path("invoicing/", include("apps.invoicing.urls", namespace="invoicing")),
    path("payments/", include("apps.payments.urls", namespace="payments")),
    path("dashboard/", include("apps.dashboard.urls", namespace="dashboard")),
]
