"""Entity-centered Company maintenance, independent of Branch context."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_safe

from core.company_forms import CompanyForm
from core.related_fields import RelatedAction, RelatedField, field_rows
from core.services.company_maintenance import (
    begin_person_creation, can_create_company, create_company, read_company_draft,
)
from core.validators.access_validator import authorized_companies
from people.models import Person
from people.services import ui_drafts as drafts


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def company_create(request):
    if not can_create_company(request.user):
        raise PermissionDenied
    token = request.POST.get("draft") if request.method == "POST" else request.GET.get("draft")
    draft = read_company_draft(request, token, state="ready") if token else None
    if request.method == "POST" and request.POST.get("action") == "cancel":
        if token:
            drafts.discard(request, token)
        return redirect("login")
    if request.method == "POST" and request.POST.get("action") == "add_person":
        # A newly created Person can only be used by its originating draft.
        if draft and draft.get("selected_person"):
            raise PermissionDenied
        if token:
            drafts.discard(request, token)
        child_token = begin_person_creation(request, request.POST)
        return redirect(reverse("person_create") + "?draft=" + child_token)
    people = Person.objects.none()
    if draft and draft.get("selected_person"):
        people = Person.objects.filter(pk=draft["selected_person"], is_active=True)
    form = CompanyForm(request.POST if request.method == "POST" else None,
                       request.FILES or None, people=people, initial=draft["data"] if draft else None)
    if request.method == "POST" and form.is_valid():
        company = create_company(request, token, form.cleaned_data)
        messages.success(request, "Empresa creada.")
        request.session["company_id"] = company.pk
        request.session["branch_id"] = None
        request.session.pop("pending_branch_id", None)
        return redirect("select_branch")
    relation = RelatedField("person", "persona", (
        RelatedAction("add", "Adicionar", "person_create", "", "action", "add_person"),
    ), "company-contextual-new-person-only", "person-independent-persistence")
    return render(request, "core/company_form.html", {
        "form": form, "draft_token": token or "",
        "field_rows": field_rows(form, {"person": relation}, request.user,
                                 allowed=not draft or not draft.get("selected_person")),
    })


@login_required
@require_safe
def company_detail(request, pk):
    if not request.user.is_active:
        raise PermissionDenied
    company = get_object_or_404(authorized_companies(request.user).filter(is_active=True)
                                .select_related("person"), pk=pk)
    return render(request, "core/company_detail.html", {"company": company})
