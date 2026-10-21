"""Shared mechanics for Company-owned commercial roles; Person stays global."""
from collections.abc import Mapping

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from core.models import Company
from core.validators.access_validator import authorized_companies
from people.services import person_access_policy


class CommercialRelationshipMaintenance:
    def __init__(self, model, fields):
        self.model = model
        self.fields = frozenset(fields)
        self.role = model._meta.model_name
        self.unique_constraint = f"people_{self.role}_company_person_unique"

    def authorize(self, actor, company, operation):
        if (
            not isinstance(company, Company)
            or company.pk is None
            or not authorized_companies(actor).filter(pk=company.pk).exists()
            or not actor.has_perm(f"people.{operation}_{self.role}")
        ):
            raise PermissionDenied

    def available_relations(self, actor, company):
        people = person_access_policy.visible_people(actor=actor, company=company)
        return self.model.objects.filter(company_id=company.pk, person_id__in=people.values('pk'))

    def validated_data(self, data, *, company=None, relation=None):
        if not isinstance(data, Mapping) or set(data) - self.fields:
            raise ValidationError('Unsupported commercial fields.', code='invalid_fields')
        result = {}
        for name, value in data.items():
            value = self.model._meta.get_field(name).clean(value, None)
            if name == 'credit_limit' and value < 0:
                raise ValidationError('Credit limit cannot be negative.', code='invalid_credit_limit')
            result[name] = value
        return result

    def expected_collision(self, error):
        cause = error.__cause__
        diagnostic = getattr(cause, 'diag', None)
        return (
            getattr(cause, 'sqlstate', None) == '23505'
            and getattr(diagnostic, 'table_name', None) == self.model._meta.db_table
            and getattr(diagnostic, 'constraint_name', None) == self.unique_constraint
        )

    def create(self, *, actor, company, person_id, data):
        try:
            with transaction.atomic():
                self.authorize(actor, company, 'add')
                person = person_access_policy.visible_people(actor=actor, company=company).filter(pk=person_id).first()
                if person is None:
                    raise person_access_policy.IdentityUnavailable
                values = self.validated_data(data, company=company)
                obj = self.model(company=company, person=person, created_by=actor, updated_by=actor, **values)
                # The database owns pair uniqueness, including concurrent INSERTs.
                obj.save(force_insert=True)
                return obj
        except IntegrityError as error:
            if self.expected_collision(error):
                raise ValidationError('Commercial relationship already exists.', code='duplicate_relationship') from None
            raise

    def list_relations(self, *, actor, company, query=None, include_inactive=False):
        self.authorize(actor, company, 'view')
        relations = self.available_relations(actor, company)
        if not include_inactive:
            relations = relations.filter(is_active=True)
        if query:
            relations = relations.filter(
                Q(person__identification__icontains=query)
                | Q(person__full_name__icontains=query)
                | Q(person__email__icontains=query)
            )
        return relations.order_by('pk')

    def relation(self, actor, company, relation_id, *, lock=False):
        relations = self.available_relations(actor, company)
        if lock:
            relations = relations.select_for_update()
        obj = relations.filter(pk=relation_id).first()
        if obj is None:
            raise ObjectDoesNotExist('Commercial relationship unavailable.')
        return obj

    def get_relation(self, *, actor, company, relation_id):
        self.authorize(actor, company, 'view')
        return self.relation(actor, company, relation_id)

    @transaction.atomic
    def update(self, *, actor, company, relation_id, data):
        self.authorize(actor, company, 'change')
        obj = self.relation(actor, company, relation_id, lock=True)
        values = self.validated_data(data, company=company, relation=obj)
        for name, value in values.items():
            setattr(obj, name, value)
        obj.updated_by = actor
        obj.save(update_fields=[*values, 'updated_by', 'updated_at'])
        return obj

    @transaction.atomic
    def set_active(self, *, actor, company, relation_id, is_active):
        self.authorize(actor, company, 'change')
        obj = self.relation(actor, company, relation_id, lock=True)
        if not isinstance(is_active, bool):
            raise ValidationError('Activity must be boolean.', code='invalid_activity')
        obj.is_active = is_active
        obj.updated_by = actor
        obj.save(update_fields=['is_active', 'updated_by', 'updated_at'])
        return obj
