from functools import wraps

from django.contrib.auth.decorators import login_required, permission_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_safe

from core.action_presentation import entity_action
from core.validators.access_validator import authorized_companies
from .forms import BrandForm, ProductForm, UnitMeasureForm
from .models import Brand, Product, UnitMeasure
from .services.product_continuation import annex_context



def _company_required(view):
    """Revalidate server-selected membership before reading catalog objects."""
    @wraps(view)
    def scoped(request, *args, **kwargs):
        selected = getattr(request, "active_company", None)
        company = authorized_companies(request.user).filter(
            pk=selected.pk if selected else None).first()
        if company is None:
            return redirect("select_company")
        request.active_company = company
        return view(request, *args, **kwargs)
    return scoped


def _save_form(form, actor, request=None):
    try:
        with transaction.atomic():
            instance = form.save(commit=False)
            if instance._state.adding:
                instance.created_by = actor
            else:
                instance.updated_by = actor
            instance.save()
            form.save_m2m()
            if request is not None and getattr(request, 'product_continuation', None):
                from .services.product_continuation import complete
                request.product_return = complete(request, instance)
    except IntegrityError:
        # Includes a concurrent unique collision after form validation. The
        # savepoint has rolled back before rendering feedback or querying again.
        form.add_error(None, "No se pudo guardar. Revise los datos e intente nuevamente.")
        return False
    return True


def _deactivate(request, instance, list_route):
    if request.method == "POST":
        with transaction.atomic():
            instance.is_active = False
            instance.deleted_at = timezone.now()
            instance.updated_by = request.user
            instance.save(update_fields=["is_active", "deleted_at", "updated_by", "updated_at"])
        return redirect(list_route)
    return render(request, "catalog/deactivate_confirm.html", {
        "object": instance, "cancel_url": list_route,
    })


def _unit_actions(actor, unit=None):
    """Explicit global catalog capabilities; endpoints recheck each permission."""
    actions = []
    declarations = [("add", "add", "Adicionar unidad", "unit_create")]
    if unit is not None:
        declarations.append(("view", "view", "Consultar unidad", "unit_detail"))
        if unit.is_active:
            declarations.extend([
                ("edit", "change", "Editar unidad", "unit_update"),
                ("delete", "delete", "Eliminar unidad", "unit_delete"),
            ])
    for icon, permission, label, route in declarations:
        if actor.has_perm(f"catalog.{permission}_unitmeasure"):
            url = reverse(route, args=[unit.pk] if route != "unit_create" else [])
            actions.append(entity_action(icon, label, url=url))
    return actions


@login_required
@permission_required("catalog.view_unitmeasure", raise_exception=True)
@require_safe
@annex_context('unit_measure', 'list')
def unit_list(request):
    units = UnitMeasure.objects.filter(is_active=True)
    return render(request, "catalog/unit_list.html", {
        "units": units,
        "add_actions": _unit_actions(request.user),
        "unit_rows": [{"unit": unit, "actions": [
            action for action in _unit_actions(request.user, unit)
            if action["url"] != reverse("unit_create")
        ]} for unit in units],
    })


@login_required
@permission_required("catalog.view_unitmeasure", raise_exception=True)
@require_safe
@annex_context('unit_measure', 'view')
def unit_detail(request, pk):
    unit = get_object_or_404(
        UnitMeasure.objects.select_related("created_by", "updated_by"), pk=pk)
    return render(request, "catalog/unit_detail.html", {
        "unit": unit, "actions": _unit_actions(request.user, unit),
    })


@login_required
@permission_required("catalog.add_unitmeasure", raise_exception=True)
@require_http_methods(["GET", "HEAD", "POST"])
@annex_context('unit_measure', 'add')
def unit_create(request):
    form = UnitMeasureForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid() and _save_form(form, request.user, request=request):
        return redirect("unit_list")
    return render(request, "catalog/unit_form.html", {"form": form, "title": "Adicionar unidad",
        "field_rows": [{"field": field, "actions": []} for field in form]})


@login_required
@permission_required("catalog.change_unitmeasure", raise_exception=True)
@require_http_methods(["GET", "HEAD", "POST"])
@annex_context('unit_measure', 'change')
def unit_update(request, pk):
    unit = get_object_or_404(UnitMeasure, pk=pk, is_active=True)
    form = UnitMeasureForm(request.POST if request.method == "POST" else None, instance=unit)
    if request.method == "POST" and form.is_valid() and _save_form(form, request.user, request=request):
        return redirect("unit_list")
    return render(request, "catalog/unit_form.html", {
        "form": form, "title": "Editar unidad",
        "field_rows": [{"field": field, "actions": []} for field in form],
        "actions": [action for action in _unit_actions(request.user, unit)
                    if action["url"] != reverse("unit_update", args=[unit.pk])],
    })


@login_required
@permission_required("catalog.delete_unitmeasure", raise_exception=True)
@require_http_methods(["GET", "HEAD", "POST"])
@annex_context('unit_measure', 'delete')
def unit_delete(request, pk):
    return _deactivate(request, get_object_or_404(UnitMeasure, pk=pk, is_active=True), "unit_list")


def _brand_actions(actor, brand=None):
    """Explicit global catalog capabilities; endpoints recheck each permission."""
    actions = []
    declarations = [("add", "add", "Adicionar marca", "brand_create")]
    if brand is not None:
        declarations.append(("view", "view", "Consultar marca", "brand_detail"))
        if brand.is_active:
            declarations.extend([
                ("edit", "change", "Editar marca", "brand_update"),
                ("delete", "delete", "Eliminar marca", "brand_delete"),
            ])
    for icon, permission, label, route in declarations:
        if actor.has_perm(f"catalog.{permission}_brand"):
            url = reverse(route, args=[brand.pk] if route != "brand_create" else [])
            actions.append(entity_action(icon, label, url=url))
    return actions


@login_required
@permission_required("catalog.view_brand", raise_exception=True)
@require_safe
@annex_context('brand', 'list')
def brand_list(request):
    brands = Brand.objects.filter(is_active=True)
    return render(request, "catalog/brand_list.html", {
        "brands": brands,
        "add_actions": _brand_actions(request.user),
        "brand_rows": [{"brand": brand, "actions": [
            action for action in _brand_actions(request.user, brand)
            if action["url"] != reverse("brand_create")
        ]} for brand in brands],
    })


@login_required
@permission_required("catalog.view_brand", raise_exception=True)
@require_safe
@annex_context('brand', 'view')
def brand_detail(request, pk):
    brand = get_object_or_404(
        Brand.objects.select_related("created_by", "updated_by"), pk=pk)
    return render(request, "catalog/brand_detail.html", {
        "brand": brand, "actions": _brand_actions(request.user, brand),
    })


@login_required
@permission_required("catalog.add_brand", raise_exception=True)
@require_http_methods(["GET", "HEAD", "POST"])
@annex_context('brand', 'add')
def brand_create(request):
    form = BrandForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid() and _save_form(form, request.user, request=request):
        return redirect("brand_list")
    return render(request, "catalog/brand_form.html", {
        "form": form, "title": "Adicionar marca",
        "field_rows": [{"field": field, "actions": []} for field in form],
    })


@login_required
@permission_required("catalog.change_brand", raise_exception=True)
@require_http_methods(["GET", "HEAD", "POST"])
@annex_context('brand', 'change')
def brand_update(request, pk):
    brand = get_object_or_404(Brand, pk=pk, is_active=True)
    form = BrandForm(request.POST if request.method == "POST" else None, instance=brand)
    if request.method == "POST" and form.is_valid() and _save_form(form, request.user, request=request):
        return redirect("brand_list")
    return render(request, "catalog/brand_form.html", {
        "form": form, "title": "Editar marca",
        "field_rows": [{"field": field, "actions": []} for field in form],
        "actions": [action for action in _brand_actions(request.user, brand)
                    if action["url"] != reverse("brand_update", args=[brand.pk])],
    })


@login_required
@permission_required("catalog.delete_brand", raise_exception=True)
@require_http_methods(["GET", "HEAD", "POST"])
@annex_context('brand', 'delete')
def brand_delete(request, pk):
    return _deactivate(request, get_object_or_404(Brand, pk=pk, is_active=True), "brand_list")


@login_required
@_company_required
@permission_required("catalog.view_product", raise_exception=True)
@require_safe
def product_list(request):
    return render(request, "catalog/product_list.html", {
        "products": Product.objects.filter(company=request.active_company, is_active=True),
    })


@login_required
@_company_required
@permission_required("catalog.view_product", raise_exception=True)
@require_safe
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, company=request.active_company, is_active=True)
    return render(request, "catalog/product_detail.html", {"product": product})


@login_required
@_company_required
@permission_required("catalog.add_product", raise_exception=True)
@require_http_methods(["GET", "HEAD", "POST"])
def product_create(request):
    return _product_form(request)

@login_required
@_company_required
@permission_required("catalog.change_product", raise_exception=True)
@require_http_methods(["GET", "HEAD", "POST"])
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk, company=request.active_company, is_active=True)
    return _product_form(request, product)

@login_required
@_company_required
@permission_required("catalog.delete_product", raise_exception=True)
@require_http_methods(["GET", "HEAD", "POST"])
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk, company=request.active_company, is_active=True)
    return _deactivate(request, product, "product_list")


def _product_form(request, product=None):
    from core.related_fields import field_rows
    from .related_fields import RELATIONS
    from .services import product_continuation as continuation
    from people.services import ui_drafts

    object_id = product.pk if product is not None else None
    restored = continuation.parent_data(request, object_id)
    data = request.POST.copy() if request.method == 'POST' else restored
    refreshing = request.method == 'POST' and request.POST.get('action') == 'refresh_group'
    if refreshing:
        continuation.clear_incompatible(request, data)
    form = ProductForm(data, instance=product, company_id=request.active_company.pk)
    if request.method == 'POST':
        response = continuation.begin(request, form, object_id)
        if response is not None:
            return response
        if not request.POST.get('related') and not refreshing and form.is_valid() and _save_form(form, request.user):
            token = continuation.token_from(request)
            if token:
                ui_drafts.discard(request, token)
            return redirect('product_list')
    definitions = {field: relation.presentation(field) for field, relation in RELATIONS.items()}
    rows = field_rows(form, definitions, request.user)
    # Inactive historical selections remain consultable, never editable here.
    for row in rows:
        field = row['field'].name
        if field == 'group':
            row['after_field_template'] = 'catalog/product_subgroup_refresh.html'
        if field == 'taxes' and not form.fields['taxes'].queryset.exists():
            row['empty_message'] = 'No hay impuestos disponibles para seleccionar'
        if field in RELATIONS:
            selected = row['field'].field.queryset.filter(pk=continuation.context_pk(row['field'].value())).first()
            if selected is not None and not selected.is_active:
                row['actions'] = [action for action in row['actions']
                                  if action['value'] != 'change:' + field]
    return render(request, 'catalog/product_form.html', {
        'form': form, 'title': 'Editar Producto' if product else 'Nuevo Producto',
        'field_rows': rows, 'draft_token': continuation.token_from(request) or '',
        'continuation_nonce': continuation.nonce(request, object_id),
    })
