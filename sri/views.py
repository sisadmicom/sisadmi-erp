from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus
from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument
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
        },
    )
