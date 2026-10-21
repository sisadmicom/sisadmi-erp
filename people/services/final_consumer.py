"""System-owned reserved identity and idempotent per-company availability."""
from contextlib import contextmanager
from contextvars import ContextVar
from django.core.exceptions import ValidationError
from django.db import transaction
from people.identification import FINAL_CONSUMER_ID

_system_creation = ContextVar('final_consumer_system_creation', default=False)
PROTECTED_MESSAGE = 'Consumidor Final es una Persona reservada, administrada exclusivamente por el sistema.'


def reject_reserved_role(person):
    if person.identification == FINAL_CONSUMER_ID:
        raise ValidationError(PROTECTED_MESSAGE, code='reserved_person_role')


@contextmanager
def system_creation():
    token = _system_creation.set(True)
    try:
        yield
    finally:
        _system_creation.reset(token)


@transaction.atomic
def ensure_person():
    """Provision the global identity without requiring an operational company."""
    from people.models import Person, IdentificationKind
    kind = IdentificationKind.objects.get(code='FINAL_CONSUMER', is_active=True)
    with system_creation():
        person, created = Person.objects.get_or_create(identification=FINAL_CONSUMER_ID,
            defaults={'full_name': 'CONSUMIDOR FINAL', 'person_type': 'NATURAL',
                      'identification_type': 'FINAL_CONSUMER', 'identification_kind': kind})
    if not created and (person.identification_type != 'FINAL_CONSUMER'
            or person.identification_kind_id != kind.pk or not person.is_active
            or person.full_name != 'CONSUMIDOR FINAL' or person.person_type != 'NATURAL'):
        raise ValidationError('La identificación reservada existente requiere revisión; no se modificó.', code='reserved_identity_conflict')
    return person


@transaction.atomic
def enable_for_company(company):
    from people.models import CompanyPersonAccess, Customer
    # Company lock serializes repeated provisioning for the same company.
    type(company).objects.select_for_update().get(pk=company.pk)
    person = ensure_person()
    CompanyPersonAccess.objects.get_or_create(company=company, person=person)
    customer, _ = Customer.objects.get_or_create(company=company, person=person)
    return customer
