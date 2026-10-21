"""Native initial-setup wizard. Intermediate POSTs write session drafts only."""

import secrets

from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from core.forms import SetupBranchForm, SetupCompanyForm, SetupLocationForm
from core.services.initial_company_setup import can_configure_company, create_initial_company
from people.forms import GEOGRAPHY, IDENTITY_UNAVAILABLE
from people.services.person_access_policy import IdentityUnavailable
from people.services import ui_drafts
from people.views import related_action


SESSION_KEY = "initial_company_setup"
STEP_FORMS = (SetupCompanyForm, SetupLocationForm, SetupBranchForm)
TITLES = ("Datos de la empresa", "Ubicación", "Sucursal principal", "Revisar y crear")


def state_for(request):
    state = request.session.get(SESSION_KEY)
    if not state or state.get("actor") != request.user.pk:
        state = {"actor": request.user.pk, "step": 0, "data": [{}, {}, {}],
                 "token": secrets.token_urlsafe(24)}
    token = request.GET.get("draft")
    if token and state.get("returned_draft") != token:
        draft = ui_drafts.read(request, token)
        if draft is None or draft["route"] != "initial_setup":
            return None
        state["data"][1] = draft["data"]
        state["step"] = 1
        state["returned_draft"] = token
    return state


def page(request, state, form=None):
    index = state["step"]
    if form is None:
        form = STEP_FORMS[index](initial=state["data"][index]) if index < 3 else forms.Form()
    geography = [{"kind": kind, "label": row[1].lower(),
                  "empty": not form.fields[kind].queryset.exists()}
                 for kind, row in GEOGRAPHY.items()] if index == 1 else []
    review = []
    if index == 3:
        for position, form_class in enumerate(STEP_FORMS):
            preview = form_class(initial=state["data"][position])
            rows = []
            for name, field in preview.fields.items():
                value = state["data"][position].get(name, "")
                if name in GEOGRAPHY:
                    value = field.queryset.filter(pk=value).first() if value else ""
                elif isinstance(field, forms.ChoiceField) and field.choices:
                    value = dict(field.choices).get(value, value)
                rows.append({"label": field.label, "value": value})
            review.append({"title": TITLES[position], "rows": rows})
    return render(request, "core/initial_setup.html", {
        "form": form, "step": index, "title": TITLES[index], "wizard_token": state["token"],
        "progress": [{"title": title, "current": i == index} for i, title in enumerate(TITLES)],
        "geography": geography, "review": review,
    })


def wizard(request):
    if not can_configure_company(request.user):
        return HttpResponseForbidden("Solicite ayuda a un administrador autorizado para configurar la empresa.")
    state = state_for(request)
    if state is None:
        return HttpResponseForbidden("El borrador ya no está disponible. Regrese a la configuración para continuar.")
    if request.method == "POST":
        if request.POST.get("wizard_token") != state["token"]:
            # A legacy single POST or stale browser page cannot confirm a draft.
            return page(request, state)
        action = request.POST.get("action")
        index = state["step"]
        if action == "cancel":
            request.session.pop(SESSION_KEY, None)
            ui_drafts.clear(request)
            return redirect("select_company")
        if index < 3:
            form = STEP_FORMS[index](request.POST)
            state["data"][index] = {name: request.POST.get(name, "") for name in form.fields}
            request.session[SESSION_KEY] = state
            if index == 1 and request.POST.get("related"):
                response = related_action(request, form, route="initial_setup")
                if response is not None:
                    return response
            if action == "previous" and index:
                state["step"] -= 1
            elif action == "refresh" and index == 1:
                pass
            elif action == "copy_address" and index == 2:
                state["data"][2]["branch_address"] = state["data"][1].get("address", "")
            elif action == "next":
                if not form.is_valid():
                    return page(request, state, form)
                state["step"] += 1
        elif action == "previous":
            state["step"] = 2
        elif action == "confirm":
            return confirm(request, state)
        request.session[SESSION_KEY] = state
        return redirect("initial_setup")
    request.session[SESSION_KEY] = state
    return page(request, state)


def confirm(request, state):
    checked = [form_class(state["data"][index]) for index, form_class in enumerate(STEP_FORMS)]
    for index, form in enumerate(checked):
        if not form.is_valid():
            state["step"] = index
            request.session[SESSION_KEY] = state
            return page(request, state, form)
    error_form = forms.Form(data={})
    try:
        company, branch = create_initial_company(
            actor=request.user, company_data=checked[0].cleaned_data,
            location_data=checked[1].cleaned_data, branch_data=checked[2].cleaned_data,
        )
    except PermissionDenied:
        return HttpResponseForbidden("Solicite ayuda a un administrador autorizado para configurar la empresa.")
    except IdentityUnavailable:
        error_form.add_error(None, IDENTITY_UNAVAILABLE)
    except (ValidationError, DatabaseError, RuntimeError):
        # Rollback has already completed. Never render exception details or
        # identities; preserve the draft so the operator can review/retry.
        error_form.add_error(None, "No se pudo crear la empresa. Revise los datos o solicite ayuda al administrador.")
    else:
        request.session["company_id"] = company.pk
        request.session["branch_id"] = branch.pk
        request.session.pop(SESSION_KEY, None)
        ui_drafts.clear(request)
        return redirect("dashboard")
    return page(request, state, error_form)
