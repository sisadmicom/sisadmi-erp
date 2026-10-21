"""Explicit company-less bootstrap; ordinary Person policy is unchanged."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from core.models import Branch, Company
from people.models import CompanyPersonAccess, Person
from people.services.person_access_policy import IdentityUnavailable, _identity_constraint_violation
from users.models import UserProfile


def can_configure_company(actor):
    return bool(actor.is_authenticated and actor.is_active and actor.is_superuser
                and UserProfile.objects.filter(user=actor).exists()
                and not Company.objects.exists())


def create_initial_company(*, actor, company_data, location_data, branch_data):
    """Validated wizard data only. The caller sets context after this commit.

    This is the explicitly authorized company-less operation. It does not
    change the authority required for ordinary Person creation/association.
    Sequential bootstrap is closed by the global Company gate; simultaneous
    empty-installation submissions are outside this slice's contract.
    """
    try:
        with transaction.atomic():
            if not can_configure_company(actor):
                raise PermissionDenied
            profile = UserProfile.objects.get(user=actor)
            identity = company_data["identification"]
            if Person.objects.filter(identification=identity).exists():
                raise IdentityUnavailable
            person = Person(
                person_type="LEGAL", identification_type=company_data["identification_type"],
                identification=identity, full_name=company_data["full_name"],
                email=company_data["email"], phone=company_data["phone"],
                country=location_data["country"], province=location_data["province"],
                canton=location_data["canton"], parish=location_data["parish"],
                address=location_data["address"], created_by=actor, updated_by=actor,
            )
            # Recheck the complete chain at the persistence boundary as well.
            if (person.country.continent_id != location_data["continent"].pk
                    or person.province.country_id != person.country_id
                    or person.canton.province_id != person.province_id
                    or person.parish.canton_id != person.canton_id):
                raise ValidationError("Revise la ubicación de la empresa.")
            person.full_clean(validate_unique=False)
            person.save()
            company = Company(person=person, commercial_name=company_data["commercial_name"],
                              created_by=actor, updated_by=actor)
            company.full_clean()
            company.save()
            from people.services.final_consumer import enable_for_company
            enable_for_company(company)
            branch = Branch(company=company, code=branch_data["branch_code"],
                            name=branch_data["branch_name"], address=branch_data["branch_address"],
                            is_main=True, created_by=actor, updated_by=actor)
            branch.full_clean()
            branch.save()
            CompanyPersonAccess.objects.create(company=company, person=person)
            profile.companies.add(company)
            profile.branches.add(branch)
    except IntegrityError as error:
        # Introspect only after rollback; normalize only the global identity
        # constraint, without exposing or reusing the existing Person.
        if _identity_constraint_violation(error):
            raise IdentityUnavailable from None
        raise
    return company, branch
