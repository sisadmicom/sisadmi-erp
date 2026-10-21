"""ERP Person and geography screens; company policy remains in D-02B.1a."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_safe, require_POST

from core.validators.access_validator import authorized_companies
from people.forms import (
    GEOGRAPHY, GEOGRAPHIC_FIELDS, IDENTITY_UNAVAILABLE, PERSON_FIELDS,
    PersonForm, geography_form, valid_id,
)
from people.services import person_access_policy as policy
from people.services import ui_drafts as drafts
from people.services import contextual_person_creation
from people.services import customer_continuation
from people.related_fields import definitions
from core.related_fields import field_rows
from core.action_presentation import entity_action
from core.services.company_maintenance import read_company_draft, return_to_company


def denied(request, text="No tiene permiso para realizar esta acción."):
    return render(request, "people/denied.html", {"explanation": text}, status=403)


def context_valid(request):
    company = request.active_company
    return bool(request.user.is_active and company and company.is_active
                and authorized_companies(request.user).filter(pk=company.pk).exists())


def scoped_people(request):
    return policy.visible_people(actor=request.user, company=request.active_company).select_related(
        "country__continent", "province", "canton", "parish"
    )


def catalog_links(request):
    return [{"label": row[2], "url": reverse(kind + "_list")}
            for kind, row in GEOGRAPHY.items() if request.user.has_perm("people.view_" + kind)]


def sections(request, form, *, person=False):
    parent = "person" if person else next((kind for kind, row in GEOGRAPHY.items()
                                           if form._meta.model is row[0]), "initial_setup")
    declared = definitions(parent)
    groups = (("Identidad", PERSON_FIELDS[:4]), ("Contacto", PERSON_FIELDS[4:6]),
              ("Ubicación", (*GEOGRAPHIC_FIELDS, "address"))) if person else (("Datos", tuple(form.fields)),)
    result = []
    for title, names in groups:
        rows = []
        for name in names:
            field = form[name]
            relation = declared.get(name)
            row = {"field": field, "actions": relation.controls(request.user, field) if relation else []}
            if name in GEOGRAPHY:
                row.update(label=GEOGRAPHY[name][1].lower(),
                           can_add=request.user.has_perm("people.add_" + name),
                           empty=not field.field.queryset.exists())
            rows.append(row)
        result.append({"title": title, "rows": rows})
    return result


def draft_state(request):
    token = request.POST.get("draft") if request.method == "POST" else request.GET.get("draft")
    draft = drafts.read(request, token)
    return token, draft


def related_action(request, form, *, route, object_id=None, parent=None):
    action = request.POST.get("related", "")
    if not action:
        return None
    try:
        operation, kind = action.split(":", 1)
    except ValueError:
        return denied(request)
    parent_entity = route.rsplit("_", 1)[0] if route != "initial_setup" else route
    relation = definitions(parent_entity).get(kind)
    capability = next((item for item in relation.actions if item.operation == operation), None) if relation else None
    if not capability or kind not in form.fields or not request.user.is_active or not request.user.has_perm(capability.permission):
        return denied(request)
    instance = None
    if operation != "add":
        instance = form.fields[kind].queryset.filter(pk=valid_id(request.POST.get(kind))).first()
        if instance is None:
            form.add_error(kind, "Seleccione primero el dato que desea mantener.")
            return None
    previous_token, previous = draft_state(request)
    if previous and previous.get("purpose") == drafts.RELATED_PURPOSE and previous.get("state") == "ready":
        # The posted form replaces this consumed snapshot, preserving its outer parent.
        drafts.discard(request, previous_token)
    token = drafts.begin_related(request, route=route, object_id=object_id,
                                 fields=form.fields, data=request.POST, parent=parent,
                                 entity=kind, operation=operation, selected=instance.pk if instance else None)
    return redirect(reverse(capability.endpoint, args=[instance.pk] if instance else []) + "?draft=" + token)


@login_required
@require_safe
def person_list(request):
    drafts.read(request, None)  # Discard expired drafts or a changed actor/context.
    if not context_valid(request) or not request.user.has_perm("people.view_person"):
        return denied(request, "Seleccione una empresa autorizada y activa y solicite permiso para consultar Personas.")
    people = scoped_people(request)
    query = request.GET.get("q", "").strip()[:250]
    if query:
        people = people.filter(Q(identification__icontains=query) | Q(full_name__icontains=query) | Q(email__icontains=query))
    can_create = policy.can_create_person(actor=request.user, company=request.active_company)
    can_edit = policy.can_administer_person(actor=request.user)
    rows = []
    for person in people.order_by("full_name", "pk"):
        actions = [entity_action("view", "Consultar persona", url=reverse("person_detail", args=[person.pk]))]
        if can_edit:
            actions.append(entity_action("edit", "Editar persona", url=reverse("person_update", args=[person.pk])))
        rows.append({"person": person, "actions": actions})
    return render(request, "people/person_list.html", {
        "people": rows, "query": query,
        "add_action": entity_action("add", "Adicionar persona", url=reverse("person_create")) if can_create else None,
        "can_create": can_create,
        "can_edit": policy.can_administer_person(actor=request.user), "catalogs": catalog_links(request),
    })


@login_required
def person_detail(request, pk):
    if not context_valid(request) or not request.user.has_perm("people.view_person"):
        return denied(request)
    person = get_object_or_404(scoped_people(request), pk=pk)
    if request.method not in {"GET", "HEAD"}:
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["GET", "HEAD"])
    return render(request, "people/person_detail.html", {
        "person": person, "can_edit": policy.can_administer_person(actor=request.user),
        "edit_action": entity_action("edit", "Editar persona", url=reverse("person_update", args=[person.pk]))
        if policy.can_administer_person(actor=request.user) else None,
    })


def person_form(request, instance=None):
    editing = instance is not None
    route = "person_update" if editing else "person_create"
    token, draft = draft_state(request)
    incoming = None
    restored = False
    initial = {}
    if token and draft and draft.get("purpose") == drafts.RELATED_PURPOSE:
        initial, incoming, restored = drafts.resolve_related(request, token, route=route,
            object_id=instance.pk if editing else None, entity="person", operation="change" if editing else "add")
        if incoming and not restored:
            raise PermissionDenied  # Person actions have a separate, approved Company policy.
        incoming = draft.get("parent")
    elif token:
        incoming = token
    outer = drafts.read(request, incoming)
    company_continuation = bool(not editing and outer and outer.get("route") == "company_create")
    customer_return = bool(not editing and outer and outer.get('purpose') == customer_continuation.PURPOSE)
    if customer_return:
        customer_continuation.read(request, incoming, state='waiting', field='person')
    if company_continuation:
        read_company_draft(request, incoming, state="awaiting_person")
    else:
        if not context_valid(request):
            if request.active_company is not None:
                drafts.clear(request)
            return denied(request, "Seleccione una empresa autorizada y activa para mantener Personas.")
        allowed = policy.can_administer_person(actor=request.user) if editing else policy.can_create_person(
            actor=request.user, company=request.active_company)
        if not allowed:
            return denied(request)
        if token and not restored and not customer_return:
            return denied(request, "El borrador ya no está disponible. Inicie el formulario nuevamente.")
        if not restored:
            initial = {key: request.GET[key] for key in GEOGRAPHIC_FIELDS if key in request.GET}
    if request.method == "POST" and request.POST.get("action") == "cancel":
        if customer_return:
            destination = customer_continuation.finish(request, incoming)
            if restored:
                drafts.discard(request, token)
            return redirect(destination)
        if company_continuation:
            destination = return_to_company(request, incoming)
            if restored:
                drafts.discard(request, token)
            return redirect(destination)
        drafts.clear(request)
        return redirect("person_list")
    form = PersonForm(request.POST if request.method == "POST" else None, instance=instance, initial=initial)
    if request.method == "POST":
        response = related_action(request, form, route=route, object_id=instance.pk if editing else None,
                                  parent=incoming if company_continuation or customer_return else None)
        if response is not None:
            return response
        if request.POST.get("action") == "refresh":
            form = PersonForm(instance=instance, initial={key: request.POST.get(key, "") for key in form.fields})
        elif not request.POST.get("related") and form.is_valid():
            try:
                if company_continuation:
                    person, destination = contextual_person_creation.create_person(request, incoming, form.cleaned_data)
                else:
                    with transaction.atomic():
                        if editing:
                            person = policy.update_person(actor=request.user, company=request.active_company,
                                person_id=instance.pk, data={key: value for key, value in form.cleaned_data.items()
                                                           if key in PERSON_FIELDS})
                        else:
                            data = {key: value for key, value in form.cleaned_data.items()
                                    if key in PERSON_FIELDS and key not in GEOGRAPHIC_FIELDS}
                            person = policy.create_person(actor=request.user, company=request.active_company, data=data)
                            for key in GEOGRAPHIC_FIELDS[1:]:
                                setattr(person, key, form.cleaned_data[key])
                            person.save(update_fields=GEOGRAPHIC_FIELDS[1:])
                        if customer_return:
                            destination = customer_continuation.finish(request, incoming, person)
            except policy.IdentityUnavailable:
                form.add_error(None, IDENTITY_UNAVAILABLE)
            except IntegrityError as error:
                if not policy._identity_constraint_violation(error):
                    raise
                form.add_error(None, IDENTITY_UNAVAILABLE)
            except ValidationError:
                form.add_error(None, "Revise los datos de la persona antes de guardar.")
            else:
                if company_continuation:
                    return redirect(destination)
                if customer_return:
                    if restored:
                        drafts.discard(request, token)
                    return redirect(destination)
                drafts.clear(request)
                messages.success(request, "Persona actualizada." if editing else "Persona registrada.")
                return redirect("person_detail", pk=person.pk)
    return render(request, "people/person_form.html", {
        "form": form, "sections": sections(request, form, person=True),
        "field_rows": field_rows(form, definitions("person"), request.user),
        "editing": editing, "draft_token": token or "", "catalogs": catalog_links(request),
        "company_continuation": company_continuation,
        "customer_continuation": customer_return,
        "entity_base": "core/entity_base.html" if company_continuation else "core/base.html",
    })


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def person_create(request):
    return person_form(request)


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def person_update(request, pk):
    if not context_valid(request) or not request.user.has_perm("people.view_person"):
        return denied(request)
    person = get_object_or_404(scoped_people(request), pk=pk)
    from people.identification import FINAL_CONSUMER_ID
    if person.identification == FINAL_CONSUMER_ID:
        from people.services.final_consumer import PROTECTED_MESSAGE
        return denied(request, PROTECTED_MESSAGE)
    return person_form(request, person)


@login_required
@require_safe
def geography_list(request, kind):
    drafts.read(request, None)
    if not request.user.is_active or not request.user.has_perm("people.view_" + kind):
        return denied(request)
    model, singular, plural, _ = GEOGRAPHY[kind]
    can_add = request.user.has_perm("people.add_" + kind)
    rows = []
    for obj in model.objects.order_by("name", "pk"):
        actions = []
        for icon, permission, endpoint, verb in (("edit", "change", "_update", "Editar"),
                                                  ("delete", "delete", "_delete", "Eliminar")):
            if request.user.has_perm("people." + permission + "_" + kind):
                actions.append(entity_action(icon, verb + " " + singular.lower(), url=reverse(kind + endpoint, args=[obj.pk])))
        rows.append({"name": obj.name, "actions": actions})
    return render(request, "people/geography_list.html", {
        "title": plural, "kind": kind, "rows": rows,
        "add_action": entity_action("add", "Adicionar " + singular.lower(), url=reverse(kind + "_create")) if can_add else None,
        "can_add": request.user.has_perm("people.add_" + kind),
        "can_edit": request.user.has_perm("people.change_" + kind), "catalogs": catalog_links(request),
    })


def geography_context(request, kind, pk, operation):
    if not request.user.is_active or not request.user.has_perm(f"people.{operation}_{kind}"):
        raise PermissionDenied
    token, draft = draft_state(request)
    route = kind + ("_create" if operation == "add" else "_delete" if operation == "delete" else "_update")
    initial, incoming, restored = drafts.resolve_related(request, token, route=route,
        object_id=pk, entity=kind, operation=operation)
    if incoming:
        validate_parent_authority(request, incoming)
    setup = bool(incoming and drafts.read(request, incoming)["route"] == "initial_setup")
    return token, initial, incoming, restored, setup


def validate_parent_authority(request, token):
    """Revalidate the explicit parent policy before operating a related catalog."""
    draft = drafts.read(request, token)
    if not draft or draft.get("purpose") != drafts.RELATED_PURPOSE or draft.get("state") != "waiting":
        raise PermissionDenied
    route, pk = draft["route"], draft["object_id"]
    if route == "initial_setup":
        from core.services.initial_company_setup import can_configure_company
        if not can_configure_company(request.user):
            raise PermissionDenied
    elif route in {"person_create", "person_update"}:
        parent = drafts.read(request, draft.get("parent"))
        if route == 'person_create' and parent and parent.get('purpose') == customer_continuation.PURPOSE:
            customer_continuation.read(request, draft['parent'], state='waiting', field='person')
            return
        if route == "person_create" and parent and parent.get("route") == "company_create":
            read_company_draft(request, draft["parent"], state="awaiting_person")
        else:
            allowed = policy.can_administer_person(actor=request.user) if pk else policy.can_create_person(
                actor=request.user, company=request.active_company)
            if not context_valid(request) or not allowed or (pk and not scoped_people(request).filter(pk=pk).exists()):
                raise PermissionDenied
    else:
        entity = route.rsplit("_", 1)[0]
        if entity not in GEOGRAPHY or route != entity + ("_update" if pk else "_create"):
            raise PermissionDenied
        if not request.user.has_perm("people." + ("change_" if pk else "add_") + entity):
            raise PermissionDenied
        if pk and not GEOGRAPHY[entity][0].objects.filter(pk=pk).exists():
            raise PermissionDenied
        if draft.get("parent"):
            validate_parent_authority(request, draft["parent"])


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def geography_edit(request, kind, pk=None):
    operation = "change" if pk is not None else "add"
    token, initial, incoming, restored, setup_company = geography_context(request, kind, pk, operation)
    model, label, _, fields = GEOGRAPHY[kind]
    instance = get_object_or_404(model, pk=pk) if pk is not None else None
    if incoming and not restored and not pk:
        source = drafts.read(request, incoming)["data"]
        initial = {field: source.get(field) for field in fields if field in GEOGRAPHY}
    form = geography_form(kind)(request.POST if request.method == "POST" else None, instance=instance, initial=initial)
    if request.method == "POST":
        if request.POST.get("action") == "cancel":
            if incoming:
                return redirect(drafts.complete_related(request, incoming, entity=kind))
            if token:
                drafts.discard(request, token)
            return redirect(kind + "_list")
        response = related_action(request, form, route=kind + ("_update" if pk else "_create"), object_id=pk, parent=incoming)
        if response is not None:
            return response
        if not request.POST.get("related") and form.is_valid():
            with transaction.atomic():
                saved = form.save(commit=False)
                if not pk:
                    saved.created_by = request.user
                saved.updated_by = request.user
                saved.save()
            messages.success(request, label + " guardado.")
            if incoming:
                return redirect(drafts.complete_related(request, incoming, entity=kind, instance=saved))
            if token:
                drafts.discard(request, token)
            return redirect(kind + "_list")
    return render(request, "people/geography_form.html", {
        "form": form, "sections": sections(request, form), "title": label,
        "editing": pk is not None, "draft_token": token or "", "catalogs": catalog_links(request),
        "setup_company": setup_company,
    })


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def geography_delete(request, kind, pk):
    token, _, incoming, _, _ = geography_context(request, kind, pk, "delete")
    from people.services.geography_deletion import has_dependencies
    from django.db.models.deletion import ProtectedError
    model, label, _, _ = GEOGRAPHY[kind]
    instance = get_object_or_404(model, pk=pk)
    error = None
    if request.method == "POST":
        if request.POST.get("action") == "cancel":
            return redirect(drafts.complete_related(request, incoming, entity=kind)) if incoming else redirect(kind + "_list")
        try:
            with transaction.atomic():
                instance = model.objects.select_for_update().get(pk=pk)
                if has_dependencies(instance):
                    raise ProtectedError("Used", [])
                instance.delete()
        except (ProtectedError, IntegrityError):
            error = "No se puede eliminar este " + label.lower() + " porque está siendo utilizado."
        else:
            if incoming:
                return redirect(drafts.complete_related(request, incoming, entity=kind, deleted=True))
            return redirect(kind + "_list")
    return render(request, "people/geography_delete.html", {
        "title": label, "object": instance, "draft_token": token or "", "error": error,
        "delete_action": entity_action("delete", "Eliminar " + label.lower()),
    })


@login_required
@require_POST
def person_identification_detect(request):
    from django.http import JsonResponse
    from people.identification import detect_identification
    if not context_valid(request) or not request.user.has_perm('people.view_person'):
        return JsonResponse({'error': 'No tiene acceso a Personas.'}, status=403)
    try:
        code = detect_identification(request.POST.get('identification', ''), request.POST.get('manual'))
    except ValidationError as error:
        return JsonResponse({'error': error.messages[0]}, status=400)
    from people.constants.identification_type import IdentificationType
    return JsonResponse({'code': code, 'label': IdentificationType(code).label,
                         'structural_only': True})
