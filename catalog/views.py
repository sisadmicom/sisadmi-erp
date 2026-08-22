from django.shortcuts import render, redirect, get_object_or_404

from .models import Product

from .forms import ProductForm

from .models import UnitMeasure

from .forms import UnitMeasureForm

from django.utils import timezone

def unit_list(request):

    units = UnitMeasure.objects.filter(
        is_active=True
    )

    return render(
        request,
        "catalog/unit_list.html",
        {
            "units": units
        }
    )


def unit_create(request):

    if request.method == "POST":

        form = UnitMeasureForm(request.POST)

        if form.is_valid():

            unit = form.save(commit=False)

            unit.created_by = request.user

            unit.save()

            return redirect("unit_list")

    else:

        form = UnitMeasureForm()

    return render(
        request,
        "catalog/unit_form.html",
        {
            "form": form,
            "title": "Nueva Unidad"
        }
    )


def unit_update(request, pk):

    unit = get_object_or_404(
        UnitMeasure,
        pk=pk,
        is_active=True
    )

    if request.method == "POST":

        form = UnitMeasureForm(
            request.POST,
            instance=unit
        )

        if form.is_valid():

            unit = form.save(commit=False)

            unit.updated_by = request.user

            unit.save()

            return redirect("unit_list")

    else:

        form = UnitMeasureForm(
            instance=unit
        )

    return render(
        request,
        "catalog/unit_form.html",
        {
            "form": form,
            "title": "Editar Unidad"
        }
    )


def unit_delete(request, pk):

    unit = get_object_or_404(
        UnitMeasure,
        pk=pk
    )

    unit.is_active = False

    unit.deleted_at = timezone.now()

    unit.updated_by = request.user

    unit.save()

    return redirect("unit_list")


def product_list(request):

    company_id = request.session.get("company_id")

    products = Product.objects.filter(
        company_id=company_id,
        is_active=True
    )

    return render(
        request,
        "catalog/product_list.html",
        {
            "products": products
        }
    )

def product_create(request):

    company_id = request.session.get("company_id")

    if request.method == "POST":

        form = ProductForm(

            request.POST,

            company_id=company_id

        )

        if form.is_valid():

            product = form.save(commit=False)

            product.company_id = company_id

            product.created_by = request.user

            product.save()

            return redirect("product_list")

    else:

        form = ProductForm(

            company_id=company_id

        )

    return render(
        request,
        "catalog/product_form.html",
        {
            "form": form,
            "title": "Nuevo Producto"
        }
    )


def product_update(request, pk):

    company_id = request.session.get("company_id")

    product = get_object_or_404(
        Product,
        pk=pk,
        company_id=company_id,
        is_active=True
    )

    if request.method == "POST":

        form = ProductForm(
            request.POST,
            instance=product,
            company_id=company_id
        )

        if form.is_valid():

            product = form.save(commit=False)

            product.updated_by = request.user

            product.save()

            return redirect("product_list")

    else:

        form = ProductForm(

            request.POST,

            instance=product,

            company_id=company_id

        )

    return render(
        request,
        "catalog/product_form.html",
        {
            "form": form,
            "title": "Editar Producto"
        }
    )


def product_delete(request, pk):

    company_id = request.session.get("company_id")

    product = get_object_or_404(
        Product,
        pk=pk,
        company_id=company_id
    )

    product.is_active = False

    product.deleted_at = timezone.now()
    product.updated_by = request.user
    product.save()

    return redirect("product_list")
