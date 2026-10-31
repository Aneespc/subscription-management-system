from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.accounts.mixins import AdminRequiredMixin

from .forms import ProductForm, ProductVariantFormSet
from .models import Product


class ProductListView(AdminRequiredMixin, ListView):
    template_name = "products/product_list.html"
    context_object_name = "products"
    paginate_by = 25

    def get_queryset(self):
        qs = Product.objects.select_related("tax").annotate(variant_count=Count("variants")).order_by("name")
        q = self.request.GET.get("q", "").strip()
        product_type = self.request.GET.get("type", "")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(notes__icontains=q))
        if product_type:
            qs = qs.filter(product_type=product_type)
        if self.request.GET.get("active") == "1":
            qs = qs.filter(is_active=True)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        context["selected_type"] = self.request.GET.get("type", "")
        context["product_types"] = Product.ProductType.choices
        context["total"] = Product.objects.count()
        context["active_total"] = Product.objects.filter(is_active=True).count()
        return context


class ProductFormView(AdminRequiredMixin, View):
    template_name = "products/product_form.html"

    def get_product(self, pk):
        return get_object_or_404(Product, pk=pk) if pk else None

    def get(self, request, pk=None):
        product = self.get_product(pk)
        return render(
            request,
            self.template_name,
            {
                "form": ProductForm(instance=product),
                "formset": ProductVariantFormSet(instance=product),
                "product": product,
                "title": f"Edit {product.name}" if product else "New Product",
            },
        )

    def post(self, request, pk=None):
        product = self.get_product(pk)
        form = ProductForm(request.POST, instance=product)
        formset = ProductVariantFormSet(request.POST, instance=product)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                product = form.save()
                formset.instance = product
                formset.save()
            messages.success(request, f"Product {product.name} saved.")
            return redirect(reverse("products:list"))
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "formset": formset,
                "product": product,
                "title": f"Edit {product.name}" if product else "New Product",
            },
        )
