"""Global reusable identification catalog; codes are system-owned semantics."""
from django.db import models
from core.models import BaseModel


class IdentificationKind(BaseModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=80)

    def clean(self):
        super().clean()
        if not self._state.adding:
            old = type(self).objects.filter(pk=self.pk).values_list('code', flat=True).first()
            if old is not None and old != self.code:
                from django.core.exceptions import ValidationError
                raise ValidationError('El código del tipo de identificación es inmutable.', code='immutable_identification_kind_code')

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name
