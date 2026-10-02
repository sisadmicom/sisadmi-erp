from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from sales.models import Sale

from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus
from sri.constants.document_status import SriDocumentStatus
from sri.constants.reception_attempt_status import SriReceptionAttemptStatus
from sri.clients.sri_reception_soap_adapter import (
    SriReceptionProtocolError,
    SriReceptionTransportError,
)
from sri.models import ElectronicDocument
from sri.services.electronic_document_reception_entrypoint import (
    submit_electronic_document,
)
from sri.services.electronic_document_authorization_entrypoint import (
    authorize_electronic_document,
)
from sri.services.electronic_document_authorization_service import (
    AuthorizationAlreadyInProgress,
    SriAuthorizationProtocolError,
    SriAuthorizationTransportError,
)
from sri.services.electronic_document_signing_service import (
    ElectronicDocumentSigningService,
)


def _workflow_presentation(document):
    """Read durable fiscal evidence; domain services still decide mutations."""
    state = document.status
    message = ""
    can_sign = state == SriDocumentStatus.GENERATED
    can_receive = state == SriDocumentStatus.SIGNED
    can_authorize = state == SriDocumentStatus.RECEIVED

    if can_receive:
        blocking_attempt = document.reception_attempts.filter(
            status__in=[
                SriReceptionAttemptStatus.IN_PROGRESS,
                SriReceptionAttemptStatus.UNCERTAIN,
            ],
        ).first()
        if blocking_attempt is not None:
            state = blocking_attempt.status
            can_receive = False
            message = (
                "La recepción está en curso."
                if state == SriReceptionAttemptStatus.IN_PROGRESS
                else "El resultado de la recepción es incierto."
            )
    elif can_authorize:
        blocking_attempt = document.authorization_attempts.filter(
            status=SriAuthorizationAttemptStatus.IN_PROGRESS,
        ).first()
        latest_attempt = blocking_attempt or document.authorization_attempts.first()
        if latest_attempt is not None:
            state = latest_attempt.status
            can_authorize = blocking_attempt is None
            messages = {
                SriAuthorizationAttemptStatus.IN_PROGRESS: "La consulta de autorización está en curso.",
                SriAuthorizationAttemptStatus.PENDING: "La autorización sigue pendiente en el SRI.",
                SriAuthorizationAttemptStatus.UNCERTAIN: "El resultado de la consulta de autorización es incierto.",
                SriAuthorizationAttemptStatus.PROTOCOL_ERROR: "La respuesta de autorización no pudo interpretarse de forma válida.",
            }
            message = messages.get(state, "")
    elif state == SriDocumentStatus.REJECTED:
        latest_authorization = document.authorization_attempts.first()
        if (
            latest_authorization is not None
            and latest_authorization.status == SriAuthorizationAttemptStatus.NOT_AUTHORIZED
        ):
            message = "El SRI rechazó la autorización del documento."
        else:
            message = "El SRI rechazó la recepción del documento."

    return {
        "workflow_state": state,
        "workflow_message": message,
        "can_sign": can_sign,
        "can_receive": can_receive,
        "can_authorize": can_authorize,
    }


def _sale_return(request, document):
    """An optional origin link must not dereference an unscoped GFK."""
    if (
        document.company_id != request.active_company.pk
        or document.branch_id != request.active_branch.pk
        or document.content_type_id != ContentType.objects.get_for_model(Sale).pk
    ):
        return None
    return Sale.objects.filter(
        pk=document.object_id,
        company=request.active_company,
        branch=request.active_branch,
    ).first()


@login_required(login_url="login")
@require_http_methods(["GET", "HEAD", "POST"])
def electronic_document_authorize(request, electronic_document_id):
    if request.active_company is None:
        return redirect("select_company")
    if request.active_branch is None:
        return redirect("select_branch")

    document = get_object_or_404(
        ElectronicDocument,
        pk=electronic_document_id,
        company=request.active_company,
        branch=request.active_branch,
    )
    state = ""
    message = "Confirme la consulta de autorización de este documento."

    if request.method == "POST":
        try:
            document = authorize_electronic_document(electronic_document=document)
        except SriAuthorizationTransportError:
            state = "UNCERTAIN"
            message = "No se pudo confirmar el resultado por un problema de comunicación con el SRI."
        except SriAuthorizationProtocolError:
            state = "PROTOCOL_ERROR"
            message = "La respuesta del SRI no pudo interpretarse de forma válida."
        except AuthorizationAlreadyInProgress:
            state = "IN_PROGRESS"
            message = "Este documento ya tiene una consulta de autorización en curso."
        except ValueError:
            state = "INVALID"
            message = "La consulta de autorización no está disponible para este documento."
        else:
            state, message = _authorization_result(document)

    return render(
        request,
        "sri/electronic_document_authorization.html",
        {
            "electronic_document": document,
            "authorization_state": state,
            "authorization_message": message,
            **_workflow_presentation(document),
            "origin_sale": _sale_return(request, document),
        },
    )


def _authorization_result(document):
    if document.status == SriDocumentStatus.AUTHORIZED:
        return "AUTHORIZED", "El documento está autorizado por el SRI."
    if document.status == SriDocumentStatus.REJECTED:
        return "REJECTED", "El SRI rechazó la autorización del documento."
    if document.status == SriDocumentStatus.RECEIVED:
        latest_attempt = document.authorization_attempts.first()
        if latest_attempt is not None and latest_attempt.status == SriAuthorizationAttemptStatus.PENDING:
            return "PENDING", "La autorización del documento sigue pendiente en el SRI."
    return "INVALID", "No hay un resultado de autorización disponible para mostrar."


@login_required(login_url="login")
@require_http_methods(["GET", "HEAD", "POST"])
def electronic_document_receive(request, electronic_document_id):
    if request.active_company is None:
        return redirect("select_company")
    if request.active_branch is None:
        return redirect("select_branch")

    document = get_object_or_404(
        ElectronicDocument,
        pk=electronic_document_id,
        company=request.active_company,
        branch=request.active_branch,
    )
    state = ""
    message = "Confirme el envío de este documento al SRI para recepción."

    if request.method == "POST":
        try:
            document = submit_electronic_document(
                electronic_document=document,
            )
        except SriReceptionTransportError:
            state = "UNCERTAIN"
            message = "No se pudo confirmar el resultado de la recepción por un problema de comunicación."
        except SriReceptionProtocolError:
            state = "UNCERTAIN"
            message = "No se pudo interpretar la respuesta de recepción del SRI."
        except ValueError:
            if document.reception_attempts.filter(
                status=SriReceptionAttemptStatus.IN_PROGRESS,
            ).exists():
                state = "IN_PROGRESS"
                message = "La recepción de este documento ya está en curso."
            else:
                state = "INVALID"
                message = "La recepción no está disponible para este documento."
        else:
            state, message = _reception_result(document)

    return render(
        request,
        "sri/electronic_document_reception.html",
        {
            "electronic_document": document,
            "reception_state": state,
            "reception_message": message,
            **_workflow_presentation(document),
            "origin_sale": _sale_return(request, document),
        },
    )


def _reception_result(document):
    if document.status == SriDocumentStatus.RECEIVED:
        return "RECEIVED", "El documento fue recibido por el SRI."
    if document.status == SriDocumentStatus.REJECTED:
        return "REJECTED", "El SRI rechazó la recepción del documento."
    return document.status, "La solicitud de recepción fue procesada."


@login_required(login_url="login")
@require_http_methods(["GET", "HEAD", "POST"])
def electronic_document_sign(request, electronic_document_id):
    if request.active_company is None:
        return redirect("select_company")
    if request.active_branch is None:
        return redirect("select_branch")

    document = get_object_or_404(
        ElectronicDocument,
        pk=electronic_document_id,
        company=request.active_company,
        branch=request.active_branch,
    )
    state = None
    message = "Confirme la firma de este documento electrónico."

    if request.method == "POST":
        try:
            document = ElectronicDocumentSigningService.sign(
                electronic_document=document,
            )
        except ValueError:
            state = "INVALID"
            message = "No se pudo completar la firma de este documento electrónico."
        else:
            state = "SIGNED"
            message = "El documento electrónico se firmó correctamente."

    return render(
        request,
        "sri/electronic_document_signing.html",
        {
            "electronic_document": document,
            "signing_state": state,
            "signing_message": message,
            **_workflow_presentation(document),
            "origin_sale": _sale_return(request, document),
        },
    )
