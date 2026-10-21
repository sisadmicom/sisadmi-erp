"""Django entrypoints for Company-owned commercial maintenance."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from people.commercial_forms import CommercialRelationshipForm
from people.models import Customer, Supplier
from people.services import customer_maintenance, supplier_maintenance, person_access_policy
from people.services.commercial_relationship_maintenance import CommercialRelationshipMaintenance
from people.services import customer_continuation, ui_drafts

ROLES = {
    'customer': (Customer, customer_maintenance, 'Clientes', 'Cliente'),
    'supplier': (Supplier, supplier_maintenance, 'Proveedores', 'Proveedor'),
}


def configuration(request, role, operation):
    model, service, title, singular = ROLES[role]
    company = request.active_company
    # Reuse the approved authorization policy also for form GET/invalid POST.
    CommercialRelationshipMaintenance(model, ()).authorize(request.user, company, operation)
    return model, service, company, {
        'title': title, 'singular': singular,
        'list_url': reverse(role + '_list'), 'create_url': reverse(role + '_create'),
        'can_add': request.user.has_perm('people.add_' + role),
        'can_change': request.user.has_perm('people.change_' + role),
        'is_customer': role == 'customer',
        'can_delete': role == 'customer' and request.user.has_perm('people.delete_customer'),
    }


def relation(service, request, company, pk):
    try:
        return service.get_relation(actor=request.user, company=company, relation_id=pk)
    except ObjectDoesNotExist:
        raise Http404 from None


def links(role, obj):
    return {
        'relation': obj, 'detail_url': reverse(role + '_detail', args=[obj.pk]),
        'edit_url': reverse(role + '_update', args=[obj.pk]),
        'delete_url': reverse('customer_delete', args=[obj.pk]) if role == 'customer' else None,
        'activity_url': reverse(role + ('_deactivate' if obj.is_active else '_reactivate'), args=[obj.pk]),
    }


@login_required
@require_safe
def commercial_list(request, role):
    _, service, company, context = configuration(request, role, 'view')
    query = request.GET.get('q', '').strip()[:250]
    include_inactive = request.GET.get('include_inactive') == '1'
    objects = service.list_relations(actor=request.user, company=company,
        query=query, include_inactive=include_inactive)
    objects = objects.select_related('person', 'category') if role == 'customer' else objects.select_related('person')
    rows = [links(role, obj) for obj in objects]
    # Empty searches must not echo a potentially unavailable identity.
    context.update(rows=rows, query=query if rows else '', include_inactive=include_inactive)
    return render(request, 'people/commercial_list.html', context)


@login_required
@require_safe
def commercial_detail(request, role, pk):
    _, service, company, context = configuration(request, role, 'view')
    context.update(links(role, relation(service, request, company, pk)))
    return render(request, 'people/commercial_detail.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def commercial_form(request, role, pk=None):
    editing = pk is not None
    model, service, company, context = configuration(request, role, 'change' if editing else 'add')
    obj = relation(service, request, company, pk) if editing else None
    local_fields = ('notes', 'credit_limit', 'category') if role == 'customer' else ('notes',)
    initial = {name: getattr(obj, name) for name in local_fields} if editing else {}
    if editing and role == 'customer':
        initial['person'] = obj.person_id
    related_error = None
    token = (request.POST.get('draft') if request.method == 'POST' else request.GET.get('draft')) if role == 'customer' else None
    if token:
        initial = customer_continuation.restore(request, token, pk)
    if role == 'customer' and request.method == 'POST' and request.POST.get('related'):
        action = request.POST['related']
        if action not in {'add:person', 'add:category'}:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        field = action.split(':')[1]
        try:
            child = customer_continuation.begin(request, pk, field)
        except ValidationError as error:
            related_error = error
        else:
            if token:
                ui_drafts.discard(request, token)
            return redirect(reverse('person_create' if field == 'person' else 'customer_category_create') + '?draft=' + child)
    form = CommercialRelationshipForm(request.POST if request.method == 'POST' else None,
        actor=request.user, company=company, model=model, editing=editing, initial=initial,
        existing_category=obj.category if editing and role == 'customer' else None,
        existing_customer=obj if editing and role == 'customer' else None)
    if related_error:
        form.add_error(None, related_error)
    if request.method == 'POST' and not related_error and form.is_valid():
        try:
            if editing:
                obj = service.update(actor=request.user, company=company, relation_id=pk, data=form.commercial_data())
            else:
                obj = service.create(actor=request.user, company=company,
                    person_id=form.cleaned_data['person'].pk, data=form.commercial_data())
        except ObjectDoesNotExist:
            raise Http404 from None
        except person_access_policy.IdentityUnavailable:
            form.add_error('person', ValidationError('La identidad no está disponible.', code='identity_unavailable'))
        except ValidationError as error:
            # Service errors contain no private identity data; preserve their codes.
            form.add_error(None, error)
        else:
            if token:
                ui_drafts.discard(request, token)
            messages.success(request, 'Relación comercial guardada.')
            return redirect(role + '_detail', pk=obj.pk)
    person_blocked = editing and role == 'customer' and customer_maintenance.has_documents(obj)
    context.update(person_documents_message=customer_maintenance.PERSON_DOCUMENTS_MESSAGE if person_blocked else '',
        person_blocked=person_blocked, form=form, editing=editing, draft_token=token or '',
        can_add_person=role == 'customer' and request.user.has_perm('people.add_person') and request.user.has_perm('people.view_person'),
        can_add_category=role == 'customer' and request.user.has_perm('people.add_customercategory'),
        form_url=reverse(role + ('_update' if editing else '_create'), args=[pk] if editing else []))
    return render(request, 'people/commercial_form.html', context)


@login_required
@require_POST
def commercial_activity(request, role, pk, is_active):
    _, service, company, _ = configuration(request, role, 'change')
    try:
        service.set_active(actor=request.user, company=company, relation_id=pk, is_active=is_active)
    except ObjectDoesNotExist:
        raise Http404 from None
    messages.success(request, 'Estado de la relación comercial actualizado.')
    return redirect(role + '_detail', pk=pk)


@login_required
@require_http_methods(['GET', 'HEAD', 'POST'])
def customer_delete(request, pk):
    _, service, company, context = configuration(request, 'customer', 'delete')
    obj = relation(service, request, company, pk)
    if request.method == 'POST' and request.POST.get('action') == 'cancel':
        return redirect('customer_list')
    blocked = service.has_dependencies(obj)
    error = ''
    if request.method == 'POST':
        if request.POST.get('confirm') != 'yes':
            error = 'Confirme expresamente que desea borrar este cliente.'
        else:
            try:
                service.delete(actor=request.user, company=company, relation_id=pk)
            except ObjectDoesNotExist:
                raise Http404 from None
            except ValidationError as failure:
                error = failure.messages[0]
                blocked = True
            else:
                messages.success(request, 'Cliente borrado. Su Persona y categoría se conservan.')
                return redirect('customer_list')
    context.update(relation=obj, blocked=blocked, error=error)
    return render(request, 'people/customer_delete.html', context)
