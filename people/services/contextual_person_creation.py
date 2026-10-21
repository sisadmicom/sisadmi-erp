"""One Person for an authorized Company/create continuation; no global scope."""
from django.db import IntegrityError, transaction

from core.services.company_maintenance import read_company_draft, return_to_company
from people.models import Person
from people.services.person_access_policy import IdentityUnavailable, _identity_constraint_violation


@transaction.atomic
def create_person(request, token, data):
    read_company_draft(request, token, state="awaiting_person")
    # PersonForm's validated Person data only. Actor and authority are server-owned.
    fields = ("person_type", "identification_type", "identification", "full_name",
              "email", "phone", "country", "province", "canton", "parish", "address")
    person = Person(**{key: data[key] for key in fields},
                    created_by=request.user, updated_by=request.user)
    person.full_clean(validate_unique=False)
    if Person.objects.filter(identification=person.identification).exists():
        raise IdentityUnavailable
    try:
        with transaction.atomic():
            person.save()
    except IntegrityError as error:
        if _identity_constraint_violation(error):
            raise IdentityUnavailable from None
        raise
    # Revalidate and consume the Person capability before returning its sole selection.
    destination = return_to_company(request, token, person=person)
    return person, destination
