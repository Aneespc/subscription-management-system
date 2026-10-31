from django.urls import path

from . import views

app_name = "plans"

urlpatterns = [
    path("", views.PlanListView.as_view(), name="list"),
    path("new/", views.PlanCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.PlanUpdateView.as_view(), name="edit"),
]
