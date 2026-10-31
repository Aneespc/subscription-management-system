from django.urls import path
from . import views

app_name = "quotations"

urlpatterns = [
    path("", views.QuotationListView.as_view(), name="list"),
    path("create/", views.QuotationCreateView.as_view(), name="create"),
    path("from-template/", views.CreateFromTemplateView.as_view(), name="from_template"),
    path("<int:pk>/", views.QuotationDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.QuotationUpdateView.as_view(), name="edit"),
    path("<int:pk>/print/", views.QuotationPrintView.as_view(), name="print"),
    path("<int:pk>/action/<str:action>/", views.QuotationActionView.as_view(), name="action"),
    path("templates/", views.TemplateListView.as_view(), name="template_list"),
    path("templates/create/", views.TemplateCreateView.as_view(), name="template_create"),
    path("templates/<int:pk>/edit/", views.TemplateUpdateView.as_view(), name="template_edit"),
]
