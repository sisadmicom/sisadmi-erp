"""First-Company authority and atomic normal Company persistence.

Only the approved empty-installation authority is supported. This does not
establish a general multi-company creation policy or an operational context.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from core.models import Company
from core.services.initial_company_setup import can_configure_company
from people.models import CompanyPersonAccess
from people.services import ui_drafts as drafts
from users.models import UserProfile


PURPOSE = "company-create-person"


def can_create_company(actor):
    return can_configure_company(actor)


def read_company_draft(request, token, *, state=None):
    draft = drafts.read(request, token)
    if not can_create_company(request.user) or not draft:
        raise PermissionDenied
    if (draft.get("actor") != request.user.pk or draft.get("company") is not None
            or draft.get("route") != "company_create" or draft.get("object_id") is not None
            or draft.get("entity") != "Company" or draft.get("operation") != "create"
            or draft.get("return_field") != "person" or draft.get("purpose") != PURPOSE
            or draft.get("state") not in {"awaiting_person", "ready"}
            or (state is not None and draft["state"] != state)):
        raise PermissionDenied
    return draft


def begin_person_creation(request, data):
    if not can_create_company(request.user):
        raise PermissionDenied
    token = drafts.save(request, route="company_create", object_id=None,
                        fields=("commercial_name",), data=data)
    drafts.update(request, token, entity="Company", operation="create",
                  return_field="person", purpose=PURPOSE,
                  state="awaiting_person", selected_person=None)
    return token


def return_to_company(request, token, *, person=None):
    draft = read_company_draft(request, token, state="awaiting_person")
    data = {"commercial_name": draft["data"].get("commercial_name", ""),
            "person": str(person.pk) if person else ""}
    draft = drafts.update(request, token, data=data, state="ready",
                          selected_person=person.pk if person else None)
    return drafts.destination(token, draft)


@transaction.atomic
def create_company(request, token, data):
    draft = read_company_draft(request, token, state="ready")
    person = data["person"]
    if not person.is_active or person.pk != draft.get("selected_person"):
        raise PermissionDenied
    profile = UserProfile.objects.select_for_update().get(user=request.user)
    # Recheck initial authority inside the Company persistence boundary.
    read_company_draft(request, token, state="ready")
    company = Company(person=person, commercial_name=data["commercial_name"],
                      logo=data.get("logo"), created_by=request.user, updated_by=request.user)
    company.full_clean()
    company.save()
    from people.services.final_consumer import enable_for_company
    enable_for_company(company)
    CompanyPersonAccess.objects.create(company=company, person=person)
    profile.companies.add(company)
    drafts.discard(request, token)
    return company
