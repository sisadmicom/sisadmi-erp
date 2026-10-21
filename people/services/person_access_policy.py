"""Company scope and separate authority over the global Person master."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction

from core.models import Company
from core.validators.access_validator import authorized_companies
from people.models import CompanyPersonAccess, Person


class IdentityUnavailable(Exception):
    def __init__(self):
        super().__init__("identity_unavailable")


def _active_actor(actor):
    return bool(
        getattr(actor, "is_authenticated", False)
        and getattr(actor, "is_active", False)
    )


def _company_access(actor, company):
    if (
        not _active_actor(actor)
        or not isinstance(company, Company)
        or company.pk is None
        or getattr(actor, "profile", None) is None
    ):
        return False
    return authorized_companies(actor).filter(pk=company.pk, is_active=True).exists()


def visible_people(*, actor, company):
    if not _company_access(actor, company) or not actor.has_perm("people.view_person"):
        return Person.objects.none()
    return Person.objects.filter(
        is_active=True, companypersonaccess__company_id=company.pk
    )


def is_available(*, actor, company, person):
    return visible_people(actor=actor, company=company).filter(pk=person.pk).exists()


def can_create_person(*, actor, company):
    return _company_access(actor, company) and actor.has_perm("people.add_person")


def can_administer_person(*, actor):
    return _active_actor(actor) and actor.has_perm("people.change_person")


def _require_association_authority(actor, company):
    if not _company_access(actor, company) or not can_administer_person(actor=actor):
        raise PermissionDenied


def associate_person(*, actor, company, person):
    _require_association_authority(actor, company)
    access, _ = CompanyPersonAccess.objects.get_or_create(company=company, person=person)
    return access


def revoke_person_access(*, actor, company, person):
    _require_association_authority(actor, company)
    from people.services.final_consumer import reject_reserved_role
    reject_reserved_role(person)
    CompanyPersonAccess.objects.filter(company=company, person=person).delete()


def _identity_constraint_violation(error):
    """Normalize only PostgreSQL uniqueness on Person.identification."""
    cause = error.__cause__
    diagnostic = getattr(cause, "diag", None)
    if (
        getattr(cause, "sqlstate", None) != "23505"
        or getattr(diagnostic, "table_name", None) != Person._meta.db_table
    ):
        return False
    # Called after the creation savepoint has rolled back, so introspection is safe.
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, Person._meta.db_table)
    constraint = constraints.get(diagnostic.constraint_name, {})
    return constraint.get("unique", False) and constraint.get("columns") == ["identification"]


def create_person(*, actor, company, data):
    if not can_create_person(actor=actor, company=company):
        raise PermissionDenied
    from people.identification import FINAL_CONSUMER_ID
    from people.services.final_consumer import PROTECTED_MESSAGE
    if data.get("identification") == FINAL_CONSUMER_ID:
        raise ValidationError(PROTECTED_MESSAGE, code="reserved_person")
    allowed_fields = {
        "identification", "identification_type", "person_type", "full_name",
        "email", "phone", "address",
    }
    if set(data) - allowed_fields:
        raise ValidationError("Unsupported person fields.")
    person = Person(**data, created_by=actor, updated_by=actor)
    # Nullable legacy geography is not part of this creation seam. Unique identity
    # is checked separately to avoid Django's identifying uniqueness messages.
    person.full_clean(
        exclude=("country", "province", "canton", "parish"), validate_unique=False
    )
    if Person.objects.filter(identification=person.identification).exists():
        raise IdentityUnavailable
    try:
        with transaction.atomic():
            person.save()
            CompanyPersonAccess.objects.create(company=company, person=person)
    except IntegrityError as error:
        if _identity_constraint_violation(error):
            raise IdentityUnavailable from None
        raise
    return person


@transaction.atomic
def update_person(*, actor, company, person_id, data):
    """Authorized descriptive edits; no privilege can override immutable identity."""
    if not _company_access(actor, company) or not can_administer_person(actor=actor):
        raise PermissionDenied
    person = visible_people(actor=actor, company=company).select_for_update().filter(pk=person_id).first()
    if person is None:
        raise IdentityUnavailable
    allowed = {'identification', 'identification_type', 'identification_kind_id',
               'person_type', 'full_name', 'email', 'phone', 'address',
               'country', 'province', 'canton', 'parish'}
    if set(data) - allowed:
        raise ValidationError('Se enviaron campos no permitidos.', code='invalid_fields')
    for name, value in data.items():
        setattr(person, name, value)
    from people.identity_integrity import assert_unchanged
    assert_unchanged(person)
    person.updated_by = actor
    person.save(update_fields=[*data, 'updated_by', 'updated_at'])
    return person
