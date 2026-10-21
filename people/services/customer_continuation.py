"""Customer related creation using the existing actor/company/session draft store."""
from django.core.exceptions import PermissionDenied, ValidationError
from people.models import Customer, CustomerCategory
from people.services import ui_drafts as drafts, person_access_policy
from people.services.commercial_relationship_maintenance import CommercialRelationshipMaintenance

PURPOSE = 'customer-related-creation'
FIELDS = ('person', 'category', 'credit_limit', 'notes')


def authority(request, pk):
    service = CommercialRelationshipMaintenance(Customer, ())
    service.authorize(request.user, request.active_company, 'change' if pk else 'add')
    if pk:
        from people.services.customer_maintenance import get_relation
        return get_relation(actor=request.user, company=request.active_company, relation_id=pk)


def read(request, token, *, state=None, field=None):
    draft = drafts.read(request, token, prune=False)
    if (not draft or draft.get('purpose') != PURPOSE
            or draft.get('session') != request.session.session_key
            or draft.get('field') not in {'person', 'category'}
            or draft.get('route') != ('customer_update' if draft.get('object_id') else 'customer_create')
            or (state and draft.get('state') != state)
            or (field and draft.get('field') != field)):
        raise PermissionDenied
    authority(request, draft['object_id'])
    permission = 'people.add_person' if draft['field'] == 'person' else 'people.add_customercategory'
    if not request.user.has_perm(permission):
        raise PermissionDenied
    if draft['field'] == 'person' and not person_access_policy.can_create_person(
            actor=request.user, company=request.active_company):
        raise PermissionDenied
    return draft


def begin(request, pk, field):
    customer = authority(request, pk)
    if field not in {'person', 'category'}:
        raise PermissionDenied
    if field == 'person' and customer is not None:
        from people.services import customer_maintenance
        if customer_maintenance.has_documents(customer):
            raise ValidationError({'person': ValidationError(customer_maintenance.PERSON_DOCUMENTS_MESSAGE, code='person_has_documents')})
    permission = 'people.add_person' if field == 'person' else 'people.add_customercategory'
    if not request.user.has_perm(permission):
        raise PermissionDenied
    if field == 'person' and not request.user.has_perm('people.view_person'):
        raise PermissionDenied
    token = drafts.save(request, route='customer_update' if pk else 'customer_create',
        object_id=pk, fields=FIELDS, data=request.POST)
    drafts.update(request, token, purpose=PURPOSE, field=field, state='waiting',
                  session=request.session.session_key)
    return token


def restore(request, token, pk):
    draft = read(request, token, state='ready')
    if draft['object_id'] != pk:
        raise PermissionDenied
    return dict(draft['data'])


def finish(request, token, instance=None):
    draft = read(request, token, state='waiting')
    data = dict(draft['data'])
    if instance is not None:
        if draft['field'] == 'person':
            from people.models import Person
            if not isinstance(instance, Person) or not person_access_policy.visible_people(
                    actor=request.user, company=request.active_company).filter(pk=instance.pk).exists():
                raise PermissionDenied
        elif not isinstance(instance, CustomerCategory) or not CustomerCategory.objects.filter(
                pk=instance.pk, company=request.active_company, is_active=True).exists():
            raise PermissionDenied
        data[draft['field']] = str(instance.pk)
    drafts.update(request, token, state='ready', data=data)
    return drafts.destination(token, draft)
