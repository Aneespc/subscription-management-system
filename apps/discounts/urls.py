from django.urls import path
from apps.discounts import views

app_name = "discounts"

urlpatterns = [
    path("", views.DiscountListView.as_view(), name="discount_list"),
    path("create/", views.DiscountCreateView.as_view(), name="discount_create"),
    path("<int:pk>/edit/", views.DiscountUpdateView.as_view(), name="discount_edit"),
]
