from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("", views.ProductListView.as_view(), name="list"),
    path("new/", views.ProductFormView.as_view(), name="create"),
    path("<int:pk>/edit/", views.ProductFormView.as_view(), name="edit"),
]
