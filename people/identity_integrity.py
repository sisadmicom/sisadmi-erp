"""Shared immutable identity contract, without personal data in errors."""
from django.core.exceptions import ValidationError

IDENTITY_FIELDS = ('identification', 'identification_type', 'identification_kind_id')
IDENTITY_MESSAGE = 'La identificación y su clasificación no pueden modificarse después de crear la Persona.'


def assert_unchanged(person):
    if person._state.adding:
        return
    previous = type(person).objects.filter(pk=person.pk).values(*IDENTITY_FIELDS).first()
    if previous and any(previous[name] != getattr(person, name) for name in IDENTITY_FIELDS):
        raise ValidationError(IDENTITY_MESSAGE, code='immutable_person_identity')


class ImmutableIdentityFormMixin:
    """Disabled display plus explicit rejection of forged POST identity values."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for name in IDENTITY_FIELDS:
                if name in self.fields:
                    self.fields[name].disabled = True
                    self.initial[name] = getattr(self.instance, name)
                    self.fields[name].required = False

    def clean(self):
        values = super().clean()
        if self.instance.pk and self.is_bound:
            for name in IDENTITY_FIELDS:
                if name in self.data:
                    submitted = self.data.getlist(name) if hasattr(self.data, 'getlist') else [self.data[name]]
                    current = str(getattr(self.instance, name) or '')
                    if any(str(value) != current for value in submitted):
                        error = ValidationError(IDENTITY_MESSAGE, code='immutable_person_identity')
                        self.add_error(name if name in self.fields else None, error)
            if 'identification_kind' in self.data:
                values_list = self.data.getlist('identification_kind') if hasattr(self.data, 'getlist') else [self.data['identification_kind']]
                if any(str(value) != str(self.instance.identification_kind_id or '') for value in values_list):
                    self.add_error(None, ValidationError(IDENTITY_MESSAGE, code='immutable_person_identity'))
            for name in IDENTITY_FIELDS:
                if name in self.fields:
                    values[name] = getattr(self.instance, name)
        return values
