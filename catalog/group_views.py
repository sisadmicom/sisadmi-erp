"""Normal ProductGroup maintenance with explicit Company and operation authority."""
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_safe

from core.action_presentation import entity_action
from .group_forms import ProductGroupMaintenanceForm
from .models import ProductGroup
from .services.product_continuation import annex_context
from .views import _company_required, _deactivate, _save_form


def _group_actions(request, group=None):
    declarations = [('add', 'add', 'Adicionar grupo', 'group_create')]
    if group is not None:
        declarations.append(('view', 'view', 'Consultar grupo', 'group_detail'))
        if group.is_active and group.company_id == request.active_company.pk:
            declarations.extend([
                ('edit', 'change', 'Editar grupo', 'group_update'),
                ('delete', 'delete', 'Eliminar grupo', 'group_delete'),
            ])
    actions = []
    for icon, permission, label, route in declarations:
        if request.user.has_perm(f'catalog.{permission}_productgroup'):
            url = reverse(route, args=[group.pk] if route != 'group_create' else [])
            actions.append(entity_action(icon, label, url=url))
    return actions


def _visible_groups(request):
    return ProductGroup.objects.filter(
        Q(company=request.active_company) | Q(company__isnull=True))


@login_required
@_company_required
@permission_required('catalog.view_productgroup', raise_exception=True)
@require_safe
@annex_context('group', 'list')
def group_list(request):
    groups = _visible_groups(request).filter(is_active=True)
    return render(request, 'catalog/group_list.html', {
        'company': request.active_company,
        'add_actions': _group_actions(request),
        'group_rows': [{'group': group, 'actions': [
            action for action in _group_actions(request, group)
            if action['url'] != reverse('group_create')
        ]} for group in groups],
    })


@login_required
@_company_required
@permission_required('catalog.view_productgroup', raise_exception=True)
@annex_context('group', 'view')
def group_detail(request, pk):
    # Resolve scope before method handling, including unauthorized POST probes.
    group = get_object_or_404(
        _visible_groups(request).select_related('created_by', 'updated_by'), pk=pk)
    if request.method not in ('GET', 'HEAD'):
        return HttpResponseNotAllowed(['GET', 'HEAD'])
    return render(request, 'catalog/group_detail.html', {
        'company': request.active_company, 'group': group,
        'actions': _group_actions(request, group),
    })


def _group_form_response(request, form, title, group=None):
    actions = _group_actions(request, group) if group is not None else []
    if group is not None:
        actions = [action for action in actions
                   if action['url'] != reverse('group_update', args=[group.pk])]
    return render(request, 'catalog/group_form.html', {
        'form': form, 'title': title, 'company': request.active_company,
        'field_rows': [{'field': field, 'actions': []} for field in form],
        'actions': actions,
    })


@login_required
@_company_required
@permission_required('catalog.add_productgroup', raise_exception=True)
@require_http_methods(['GET', 'HEAD', 'POST'])
@annex_context('group', 'add')
def group_create(request):
    form = ProductGroupMaintenanceForm(
        request.POST if request.method == 'POST' else None, company=request.active_company)
    if request.method == 'POST' and form.is_valid() and _save_form(form, request.user, request=request):
        return redirect('group_list')
    return _group_form_response(request, form, 'Adicionar grupo')


@login_required
@_company_required
@permission_required('catalog.change_productgroup', raise_exception=True)
@require_http_methods(['GET', 'HEAD', 'POST'])
@annex_context('group', 'change')
def group_update(request, pk):
    group = get_object_or_404(ProductGroup, pk=pk, company=request.active_company, is_active=True)
    form = ProductGroupMaintenanceForm(
        request.POST if request.method == 'POST' else None,
        instance=group, company=request.active_company)
    if request.method == 'POST' and form.is_valid() and _save_form(form, request.user, request=request):
        return redirect('group_list')
    return _group_form_response(request, form, 'Editar grupo', group)


@login_required
@_company_required
@permission_required('catalog.delete_productgroup', raise_exception=True)
@require_http_methods(['GET', 'HEAD', 'POST'])
@annex_context('group', 'delete')
def group_delete(request, pk):
    group = get_object_or_404(ProductGroup, pk=pk, company=request.active_company, is_active=True)
    return _deactivate(request, group, 'group_list')
