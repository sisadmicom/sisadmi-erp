"""Reserved global identity guards, including queryset and cascade operations."""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import pre_delete, pre_save
from people.identification import FINAL_CONSUMER_ID
from people.services.final_consumer import PROTECTED_MESSAGE


class PersonQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if self.filter(identification=FINAL_CONSUMER_ID).exists():
            raise ValidationError(PROTECTED_MESSAGE, code='reserved_person')
        # Expressions and same-value assignments are decided atomically by PostgreSQL.
        return super().update(**kwargs)

    def delete(self):
        # Check before Django collects PROTECT relations, for a stable domain error.
        if self.filter(identification=FINAL_CONSUMER_ID).exists():
            raise ValidationError(PROTECTED_MESSAGE, code='reserved_person')
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        raise ValidationError('Las Personas requieren creación individual validada.', code='identity_bulk_create')


def protect_delete(sender, instance, **kwargs):
    if instance.identification == FINAL_CONSUMER_ID or sender.objects.filter(pk=instance.pk, identification=FINAL_CONSUMER_ID).exists():
        raise ValidationError(PROTECTED_MESSAGE, code='reserved_person')


def protect_role(sender, instance, **kwargs):
    from people.services.final_consumer import reject_reserved_role
    reject_reserved_role(instance.person)


def register():
    from people.models import Person, Supplier, Employee
    from core.models import Company
    pre_delete.connect(protect_delete, sender=Person, dispatch_uid='people.reserved.delete')
    for model in (Supplier, Employee, Company):
        pre_save.connect(protect_role, sender=model, dispatch_uid='people.reserved.role.' + model._meta.label)
