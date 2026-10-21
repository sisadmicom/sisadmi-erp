"""Normal ProductSubGroup maintenance with explicit Company and operation authority."""
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_safe

from core.action_presentation import entity_action
from .subgroup_forms import ProductSubGroupMaintenanceForm
from .models import ProductSubGroup
from .services.product_continuation import annex_context
from .views import _company_required, _deactivate, _save_form


def _subgroup_actions(request, subgroup=None):
    declarations = [('add', 'add', 'Adicionar subgrupo', 'subgroup_create')]
    if subgroup is not None:
        declarations.append(('view', 'view', 'Consultar subgrupo', 'subgroup_detail'))
        if subgroup.is_active and subgroup.company_id == request.active_company.pk:
            declarations.extend([
                ('edit', 'change', 'Editar subgrupo', 'subgroup_update'),
                ('delete', 'delete', 'Eliminar subgrupo', 'subgroup_delete'),
            ])
    actions = []
    for icon, permission, label, route in declarations:
        if request.user.has_perm(f'catalog.{permission}_productsubgroup'):
            url = reverse(route, args=[subgroup.pk] if route != 'subgroup_create' else [])
            actions.append(entity_action(icon, label, url=url))
    return actions


def _visible_subgroups(request):
    return ProductSubGroup.objects.filter(company=request.active_company).select_related('group')


@login_required
@_company_required
@permission_required('catalog.view_productsubgroup', raise_exception=True)
@require_safe
@annex_context('subgroup', 'list')
def subgroup_list(request):
    subgroups = _visible_subgroups(request).filter(is_active=True)
    return render(request, 'catalog/subgroup_list.html', {
        'company': request.active_company,
        'add_actions': _subgroup_actions(request),
        'subgroup_rows': [{'subgroup': subgroup, 'actions': [
            action for action in _subgroup_actions(request, subgroup)
            if action['url'] != reverse('subgroup_create')
        ]} for subgroup in subgroups],
    })


@login_required
@_company_required
@permission_required('catalog.view_productsubgroup', raise_exception=True)
@annex_context('subgroup', 'view')
def subgroup_detail(request, pk):
    # Resolve scope before method handling, including unauthorized POST probes.
    subgroup = get_object_or_404(
        _visible_subgroups(request).select_related('created_by', 'updated_by'), pk=pk)
    if request.method not in ('GET', 'HEAD'):
        return HttpResponseNotAllowed(['GET', 'HEAD'])
    return render(request, 'catalog/subgroup_detail.html', {
        'company': request.active_company, 'subgroup': subgroup,
        'actions': _subgroup_actions(request, subgroup),
    })


def _subgroup_form_response(request, form, title, subgroup=None):
    actions = _subgroup_actions(request, subgroup) if subgroup is not None else []
    if subgroup is not None:
        actions = [action for action in actions
                   if action['url'] != reverse('subgroup_update', args=[subgroup.pk])]
    return render(request, 'catalog/subgroup_form.html', {
        'form': form, 'title': title, 'company': request.active_company,
        'field_rows': [{'field': field, 'actions': []} for field in form],
        'actions': actions,
    })


@login_required
@_company_required
@permission_required('catalog.add_productsubgroup', raise_exception=True)
@require_http_methods(['GET', 'HEAD', 'POST'])
@annex_context('subgroup', 'add')
def subgroup_create(request):
    form = ProductSubGroupMaintenanceForm(
        request.POST if request.method == 'POST' else None, company=request.active_company, related_group_id=(
            request.product_continuation['draft']['data'].get('group')
            if getattr(request, 'product_continuation', None) else None))
    if request.method == 'POST' and form.is_valid() and _save_form(form, request.user, request=request):
        return redirect('subgroup_list')
    return _subgroup_form_response(request, form, 'Adicionar subgrupo')


@login_required
@_company_required
@permission_required('catalog.change_productsubgroup', raise_exception=True)
@require_http_methods(['GET', 'HEAD', 'POST'])
@annex_context('subgroup', 'change')
def subgroup_update(request, pk):
    subgroup = get_object_or_404(ProductSubGroup, pk=pk, company=request.active_company, is_active=True)
    form = ProductSubGroupMaintenanceForm(
        request.POST if request.method == 'POST' else None,
        instance=subgroup, company=request.active_company, related_group_id=(
            request.product_continuation['draft']['data'].get('group')
            if getattr(request, 'product_continuation', None) else None))
    if request.method == 'POST' and form.is_valid() and _save_form(form, request.user, request=request):
        return redirect('subgroup_list')
    return _subgroup_form_response(request, form, 'Editar subgrupo', subgroup)


@login_required
@_company_required
@permission_required('catalog.delete_productsubgroup', raise_exception=True)
@require_http_methods(['GET', 'HEAD', 'POST'])
@annex_context('subgroup', 'delete')
def subgroup_delete(request, pk):
    subgroup = get_object_or_404(ProductSubGroup, pk=pk, company=request.active_company, is_active=True)
    return _deactivate(request, subgroup, 'subgroup_list')
