"""Explicit Product continuations in the existing session draft store."""
import secrets
from functools import wraps

from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import QueryDict
from django.shortcuts import redirect
from django.urls import reverse

from core.validators.access_validator import authorized_companies, context_pk
from people.services import ui_drafts as drafts
from catalog.forms import ProductForm
from catalog.models import Product, ProductSubGroup
from catalog.related_fields import RELATIONS

PURPOSE = 'product-related-maintenance'
SALT = 'catalog.product.continuation'


def token_from(request):
    posted, query = request.POST.get('draft'), request.GET.get('draft')
    if posted and query and posted != query:
        raise PermissionDenied
    return posted or query


def authority(request, object_id=None):
    company = getattr(request, 'active_company', None)
    if not company or not authorized_companies(request.user).filter(pk=company.pk).exists():
        raise PermissionDenied
    operation = 'change' if object_id is not None else 'add'
    if not request.user.has_perm('catalog.' + operation + '_product'):
        raise PermissionDenied
    if object_id is not None:
        product = Product.objects.filter(pk=object_id, company=company, is_active=True).first()
        if product is None:
            raise PermissionDenied
        return product


def read(request, token):
    draft = drafts.read(request, token, prune=False)
    if not draft or draft.get('purpose') != PURPOSE or draft.get('session') != request.session.session_key:
        raise PermissionDenied('La continuación ya no está disponible. Vuelva al producto.')
    authority(request, draft['object_id'])
    relation = RELATIONS.get(draft.get('field'))
    if (not relation or draft.get('entity') != relation.entity
            or draft.get('operation') not in ('add', 'view', 'change')
            or draft.get('parent_operation') != ('change' if draft['object_id'] is not None else 'add')
            or draft.get('route') != ('product_update' if draft['object_id'] is not None else 'product_create')
            or not request.user.has_perm(relation.permission(draft['operation']))):
        raise PermissionDenied
    return draft


def bound_data(data):
    result = QueryDict('', mutable=True)
    for key, value in data.items():
        if isinstance(value, list):
            result.setlist(key, value)
        elif isinstance(value, bool):
            if value:
                result[key] = 'on'
        else:
            result[key] = value
    return result


def parent_data(request, object_id):
    token = token_from(request)
    if not token:
        return None
    draft = read(request, token)
    if draft['object_id'] != object_id or draft['state'] != 'ready':
        raise PermissionDenied
    return bound_data(draft['data'])


def nonce(request, object_id):
    return signing.dumps({'actor': request.user.pk, 'session': request.session.session_key,
                          'company': request.active_company.pk, 'product': object_id,
                          'random': secrets.token_urlsafe(24)}, salt=SALT)


def begin(request, form, object_id):
    action = request.POST.get('related', '')
    if not action:
        return None
    try:
        operation, field = action.split(':', 1)
        relation = RELATIONS[field]
        endpoint = relation.endpoint(operation)
        stamp = signing.loads(request.POST.get('continuation_nonce', ''), salt=SALT, max_age=drafts.MAX_AGE)
    except (KeyError, ValueError, signing.BadSignature):
        raise PermissionDenied
    authority(request, object_id)
    if (stamp.get('actor') != request.user.pk or stamp.get('session') != request.session.session_key
            or stamp.get('company') != request.active_company.pk
            or not request.user.has_perm(relation.permission(operation))):
        raise PermissionDenied
    selected = None
    if operation != 'add':
        selected = form.fields[field].queryset.filter(pk=context_pk(request.POST.get(field))).first()
        if selected is None or (operation == 'change' and not selected.is_active):
            raise PermissionDenied
    if field == 'subgroup' and operation == 'add':
        if not form.fields['group'].queryset.filter(pk=context_pk(request.POST.get('group')), is_active=True).exists():
            form.add_error('group', 'Seleccione un grupo disponible antes de adicionar un subgrupo.')
            return None
    previous, draft = drafts.find(request, purpose=PURPOSE, nonce=request.POST['continuation_nonce'],
                                   field=field, operation=operation, object_id=object_id)
    if previous:
        if draft['state'] != 'waiting' or draft['selected'] != (selected.pk if selected else None):
            raise PermissionDenied
        return redirect(reverse(endpoint, args=[selected.pk] if selected else []) + '?draft=' + previous)
    route = 'product_update' if object_id is not None else 'product_create'
    token = drafts.save(request, route=route, object_id=object_id, fields=form.fields,
                        data=request.POST, multiple=('taxes',), booleans=('is_service', 'stock_control'))
    drafts.update(request, token, purpose=PURPOSE, state='waiting', field=field, entity=relation.entity,
                  operation=operation, selected=selected.pk if selected else None,
                  parent_operation='change' if object_id is not None else 'add',
                  session=request.session.session_key, nonce=request.POST['continuation_nonce'])
    return redirect(reverse(endpoint, args=[selected.pk] if selected else []) + '?draft=' + token)


def clear_incompatible(request, data):
    if data.get('subgroup') and not ProductSubGroup.objects.filter(
            pk=context_pk(data['subgroup']), company=request.active_company,
            group_id=context_pk(data.get('group'))).exists():
        data['subgroup'] = ''
        messages.info(request, 'Se quitó el subgrupo porque no corresponde al grupo seleccionado.')


def complete(request, instance=None):
    context = request.product_continuation
    draft = read(request, context['token'])
    if draft['state'] != 'waiting':
        raise PermissionDenied
    data = dict(draft['data'])
    if instance is not None:
        if draft['operation'] == 'change' and instance.pk != draft['selected']:
            raise PermissionDenied
        product = authority(request, draft['object_id'])
        form = ProductForm(bound_data(data), instance=product, company_id=request.active_company.pk)
        field = draft['field']
        if field == 'subgroup' and draft['operation'] == 'change':
            # The authorized subgroup may have moved; keep Group and clear an
            # incompatible selection rather than silently reparenting Product.
            if instance.company_id != request.active_company.pk or not instance.is_active:
                raise PermissionDenied
        elif not form.fields[field].queryset.filter(pk=instance.pk).exists():
            raise PermissionDenied
        data[field] = str(instance.pk)
        if field in ('group', 'subgroup'):
            clear_incompatible(request, data)
    drafts.update(request, context['token'], state='ready', data=data)
    return drafts.destination(context['token'], draft)


def annex_context(field, operation):
    """Decorate fixed normal routes; never resolve browser-supplied model names."""
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            token = token_from(request)
            if not token:
                return view(request, *args, **kwargs)
            draft = read(request, token)
            pk = kwargs.get('pk')
            if (draft['state'] != 'waiting' or draft['field'] != field
                    or draft['operation'] != operation or draft['selected'] != pk):
                raise PermissionDenied
            product = authority(request, draft['object_id'])
            if pk is not None:
                form = ProductForm(bound_data(draft['data']), instance=product, company_id=request.active_company.pk)
                if not form.fields[field].queryset.filter(pk=pk).exists():
                    raise PermissionDenied
            request.product_continuation = {'token': token, 'draft': draft,
                                            'return_url': drafts.destination(token, draft)}
            if request.method == 'POST' and request.POST.get('action') == 'cancel':
                return redirect(complete(request))
            response = view(request, *args, **kwargs)
            if operation == 'view' and response.status_code == 200:
                complete(request)
            if response.status_code == 302 and getattr(request, 'product_return', None):
                return redirect(request.product_return)
            return response
        return wrapped
    return decorate
