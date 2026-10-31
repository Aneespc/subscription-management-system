from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("switch/<str:username>/", views.switch_user, name="switch_user"),
]
