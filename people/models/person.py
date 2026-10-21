from django.core.exceptions import ValidationError
from django.db import models

from people.constants.identification_type import IdentificationType

from core.models import BaseModel

from people.models.geography import (
    Country,
    Province,
    Canton,
    Parish
)


from people.services.person_protection import PersonQuerySet


class Person(BaseModel):
    objects = PersonQuerySet.as_manager()

    PERSON_TYPES=(
        ("NATURAL","Natural"),
        ("LEGAL","Jurídica")
    )

    identification=models.CharField(
        max_length=20,
        unique=True
    )

    identification_type = models.CharField(
        max_length=20,
        choices=IdentificationType.choices,
        null=True,
        blank=True,
    )

    person_type=models.CharField(
        max_length=10,
        choices=PERSON_TYPES
    )

    full_name=models.CharField(
        max_length=250
    )

    email=models.EmailField(
        blank=True,
        null=True
    )

    phone=models.CharField(
        max_length=30,
        blank=True
    )

    country=models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        null=True
    )

    province=models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        null=True
    )

    canton=models.ForeignKey(
        Canton,
        on_delete=models.PROTECT,
        null=True
    )

    parish=models.ForeignKey(
        Parish,
        on_delete=models.PROTECT,
        null=True
    )

    address=models.TextField(
        blank=True
    )

    identification_kind = models.ForeignKey(
        "people.IdentificationKind", on_delete=models.PROTECT, null=True, blank=True,
    )

    def _identity_changed(self):
        if self._state.adding:
            return True
        previous = type(self).objects.filter(pk=self.pk).values('identification', 'identification_type', 'identification_kind_id').first()
        return previous is None or any(previous[name] != getattr(self, name) for name in previous)

    def clean(self):
        super().clean()
        from people.identity_integrity import assert_unchanged
        assert_unchanged(self)
        # Existing unmodified identities keep their historical classification.
        if self.identification and self._identity_changed():
            from people.identification import detect_identification
            self.identification_type = detect_identification(self.identification, self.identification_type)

    def save(self, *args, **kwargs):
        from people.identification import FINAL_CONSUMER_ID
        from people.services.final_consumer import _system_creation, PROTECTED_MESSAGE
        old_reserved = self.pk and type(self).objects.filter(pk=self.pk, identification=FINAL_CONSUMER_ID).exists()
        if old_reserved or (self.identification == FINAL_CONSUMER_ID and not _system_creation.get()):
            raise ValidationError(PROTECTED_MESSAGE, code='reserved_person')
        from people.identity_integrity import assert_unchanged
        assert_unchanged(self)
        if self._state.adding:
            self.clean()
            from people.models.identification_kind import IdentificationKind
            kind = IdentificationKind.objects.filter(code=self.identification_type, is_active=True).first()
            if kind is None or (self.identification_kind_id is not None and self.identification_kind_id != kind.pk):
                raise ValidationError('El tipo y el catálogo de identificación no son coherentes.', code='incoherent_person_identity')
            self.identification_kind = kind
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'identification_type', 'identification_kind'}
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from people.services.final_consumer import reject_reserved_role
        reject_reserved_role(self)
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.identification} - {self.full_name}"