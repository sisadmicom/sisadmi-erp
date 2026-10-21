"""Authorized Company-scoped customer maintenance; no Branch requirement."""
from collections.abc import Mapping
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from core.validators.access_validator import context_pk
from people.models import Customer, CustomerCategory
from people.services.commercial_relationship_maintenance import CommercialRelationshipMaintenance

class CustomerMaintenance(CommercialRelationshipMaintenance):
    def relation(self, actor, company, relation_id, *, lock=False):
        if not lock:
            return super().relation(actor, company, relation_id)
        # Public mutating operations authorize first and already own an atomic
        # transaction. Lock only stable identity; person_id may change while waiting.
        customer = self.model.objects.filter(
            company_id=company.pk, pk=relation_id,
        ).select_for_update().first()
        from people.services import person_access_policy
        if customer is None or not person_access_policy.visible_people(
                actor=actor, company=company).filter(pk=customer.person_id).exists():
            raise ObjectDoesNotExist('Commercial relationship unavailable.')
        return customer

    def validated_data(self, data, *, company=None, relation=None):
        if not isinstance(data, Mapping):
            return super().validated_data(data, company=company, relation=relation)
        result = super().validated_data(
            {name: value for name, value in data.items() if name != 'category'},
            company=company, relation=relation,
        )
        if 'category' not in data:
            return result  # Partial edits preserve the persisted category.
        value = data['category']
        if value is None or value == '':
            result['category'] = None
            return result
        pk = context_pk(value.pk if isinstance(value, CustomerCategory) else value)
        category = CustomerCategory.objects.select_for_update().filter(company=company, pk=pk).first()
        if category is None or (not category.is_active and
                                (relation is None or relation.category_id != category.pk)):
            raise ValidationError({'category': ValidationError(
                'La categoría no está disponible en esta empresa.', code='invalid_category',
            )})
        result['category'] = category
        return result


_service = CustomerMaintenance(Customer, ('notes', 'credit_limit', 'category'))


def create(*, actor, company, person_id, data):
    return _service.create(actor=actor, company=company, person_id=person_id, data=data)


def list_relations(*, actor, company, query=None, include_inactive=False):
    return _service.list_relations(actor=actor, company=company, query=query, include_inactive=include_inactive)


def get_relation(*, actor, company, relation_id):
    return _service.get_relation(actor=actor, company=company, relation_id=relation_id)


def update(*, actor, company, relation_id, data):
    if not isinstance(data, Mapping) or 'person' not in data:
        return _service.update(actor=actor, company=company, relation_id=relation_id, data=data)
    from people.services import person_access_policy
    from people.models import Person
    try:
        with transaction.atomic():
            _service.authorize(actor, company, 'change')
            customer = _service.relation(actor, company, relation_id, lock=True)
            value = data['person']
            pk = context_pk(value.pk if isinstance(value, Person) else value)
            person = person_access_policy.visible_people(actor=actor, company=company).filter(pk=pk).first()
            if person is None:
                raise ValidationError({'person': ValidationError(
                    'La Persona no está disponible en esta empresa.', code='identity_unavailable')})
            if person.pk != customer.person_id and has_documents(customer):
                raise ValidationError({'person': ValidationError(PERSON_DOCUMENTS_MESSAGE, code='person_has_documents')})
            values = _service.validated_data({key: value for key, value in data.items() if key != 'person'},
                                             company=company, relation=customer)
            if Customer.objects.filter(company=company, person=person).exclude(pk=customer.pk).exists():
                raise ValidationError({'person': ValidationError(
                    'Esta Persona ya está registrada como cliente de la empresa.', code='duplicate_relationship')})
            values['person'] = person
            for name, value in values.items():
                setattr(customer, name, value)
            customer.updated_by = actor
            customer.save(update_fields=[*values, 'updated_by', 'updated_at'])
            return customer
    except IntegrityError as error:
        if _service.expected_collision(error):
            raise ValidationError({'person': ValidationError(
                'Esta Persona ya está registrada como cliente de la empresa.', code='duplicate_relationship')}) from None
        raise


def set_active(*, actor, company, relation_id, is_active):
    return _service.set_active(actor=actor, company=company, relation_id=relation_id, is_active=is_active)


def has_dependencies(customer):
    from people.services.geography_deletion import has_dependencies as has_references
    if has_references(customer):
        return True
    # Generic references lack database FK protection; check their explicit types.
    from django.apps import apps
    from django.contrib.contenttypes.fields import GenericForeignKey
    from django.contrib.contenttypes.models import ContentType
    for model in apps.get_models():
        for field in model._meta.private_fields:
            if isinstance(field, GenericForeignKey):
                content_type = ContentType.objects.get_for_model(customer, for_concrete_model=field.for_concrete_model)
                if model._base_manager.filter(**{field.ct_field: content_type, field.fk_field: customer.pk}).exists():
                    return True
    return False


@transaction.atomic
def delete(*, actor, company, relation_id):
    _service.authorize(actor, company, 'delete')
    customer = _service.relation(actor, company, relation_id, lock=True)
    message = 'No se puede borrar el cliente porque tiene documentos u otros registros relacionados.'
    if has_dependencies(customer):
        raise ValidationError(message, code='customer_in_use')
    try:
        with transaction.atomic():
            customer.delete()
    except (ProtectedError, RestrictedError):
        raise ValidationError(message, code='customer_in_use') from None
    except IntegrityError as error:
        if getattr(error.__cause__, 'sqlstate', None) == '23503':
            raise ValidationError(message, code='customer_in_use') from None
        raise


PERSON_DOCUMENTS_MESSAGE = 'No se puede cambiar la Persona porque el cliente tiene documentos asociados. Se conserva la Persona original.'


def has_documents(customer):
    from core.models import BaseDocument
    from django.apps import apps
    from django.contrib.contenttypes.fields import GenericForeignKey
    from django.contrib.contenttypes.models import ContentType
    # Includes every state, including drafts, and future concrete document FKs.
    for relation in customer._meta.related_objects:
        if issubclass(relation.related_model, BaseDocument) and relation.related_model._base_manager.filter(
                **{relation.field.name: customer}).exists():
            return True
    # ElectronicDocument and StockMovement use explicit generic document links.
    for model in apps.get_models():
        for field in model._meta.private_fields:
            if isinstance(field, GenericForeignKey) and field.name == 'document':
                content_type = ContentType.objects.get_for_model(customer, for_concrete_model=field.for_concrete_model)
                if model._base_manager.filter(**{field.ct_field: content_type, field.fk_field: customer.pk}).exists():
                    return True
    return False
