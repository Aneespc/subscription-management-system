from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("", views.SubscriptionListView.as_view(), name="list"),
    path("plans/", views.PlanCatalogView.as_view(), name="plans"),
    path("plans/<int:pk>/subscribe/", views.SubscribeView.as_view(), name="subscribe"),
    path("create/", views.SubscriptionFormView.as_view(), name="create"),
    path("<int:pk>/", views.SubscriptionDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.SubscriptionFormView.as_view(), name="edit"),
    path("<int:pk>/action/<str:action>/", views.SubscriptionActionView.as_view(), name="action"),
]
