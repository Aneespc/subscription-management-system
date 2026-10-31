from django.urls import path
from . import views

app_name = "subscriptions"

urlpatterns = [
    path("", views.SubscriptionListView.as_view(), name="list"),
    path("plans/", views.SelectPlanView.as_view(), name="select_plan"),
    path("create/", views.SubscriptionCreateView.as_view(), name="create"),
    path("<int:pk>/", views.SubscriptionDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.SubscriptionUpdateView.as_view(), name="edit"),
    path("<int:pk>/action/<str:action>/", views.SubscriptionActionView.as_view(), name="action"),
]
