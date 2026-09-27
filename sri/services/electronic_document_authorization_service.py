from dataclasses import dataclass
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.constants.sri import SriEnvironment
from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus
from sri.constants.document_status import SriDocumentStatus
from sri.models.electronic_document import ElectronicDocument
from sri.models.sri_authorization_attempt import SriAuthorizationAttempt
from sri.models.sri_authorization_message import SriAuthorizationMessage


class SriAuthorizationTransportError(RuntimeError):
    pass


class SriAuthorizationProtocolError(ValueError):
    pass


class AuthorizationAlreadyInProgress(RuntimeError):
    pass


@dataclass(frozen=True)
class SriAuthorizationMessageData:
    message_type: str | None
    identifier: str | None
    message: str
    additional_information: str | None


@dataclass(frozen=True)
class SriAuthorizationResult:
    outcome: str
    access_key_consulted: str
    authorization_number: str | None = None
    authorization_date: datetime | None = None
    environment: str | None = None
    authorized_xml: str | None = None
    messages: tuple[SriAuthorizationMessageData, ...] = ()


class ElectronicDocumentAuthorizationService:
    @staticmethod
    def authorize(*, electronic_document, adapter):
        if not isinstance(electronic_document, ElectronicDocument) or not electronic_document.pk:
            raise ValueError("Se requiere un ElectronicDocument persistido.")
        with transaction.atomic():
            document = ElectronicDocument.objects.select_for_update().get(pk=electronic_document.pk)
            if document.status == SriDocumentStatus.AUTHORIZED:
                return document
            access_key, environment = ElectronicDocumentAuthorizationService._preflight(document)
            if SriAuthorizationAttempt.objects.filter(electronic_document=document, status=SriAuthorizationAttemptStatus.IN_PROGRESS).exists():
                raise AuthorizationAlreadyInProgress("El documento ya tiene una autorización en progreso.")
            try:
                attempt = SriAuthorizationAttempt.objects.create(
                    electronic_document=document,
                    status=SriAuthorizationAttemptStatus.IN_PROGRESS,
                    access_key=access_key,
                    environment=environment,
                    started_at=timezone.now(),
                )
            except IntegrityError as exc:
                raise AuthorizationAlreadyInProgress("El documento ya tiene una autorización en progreso.") from exc
        try:
            result = adapter.query_authorization(access_key=access_key, environment=environment)
            return ElectronicDocumentAuthorizationService._finalize_result(document.pk, attempt.pk, result)
        except SriAuthorizationTransportError as exc:
            ElectronicDocumentAuthorizationService._finalize_error(document.pk, attempt.pk, SriAuthorizationAttemptStatus.UNCERTAIN, exc)
            raise
        except SriAuthorizationProtocolError as exc:
            ElectronicDocumentAuthorizationService._finalize_error(document.pk, attempt.pk, SriAuthorizationAttemptStatus.PROTOCOL_ERROR, exc)
            raise
        except Exception as exc:
            ElectronicDocumentAuthorizationService._finalize_error(document.pk, attempt.pk, SriAuthorizationAttemptStatus.UNCERTAIN, exc)
            raise

    @staticmethod
    def _preflight(document):
        if document.status != SriDocumentStatus.RECEIVED:
            raise ValueError("Solo se pueden autorizar documentos recibidos.")
        if not document.access_key:
            raise ValueError("El documento electrónico no tiene clave de acceso.")
        valid = {value for value, _ in SriEnvironment.CHOICES}
        if document.environment not in valid:
            raise ValueError("El ambiente SRI no es válido.")
        return document.access_key, document.environment

    @staticmethod
    def _validate_result(document, result):
        required = ("outcome", "access_key_consulted", "authorization_number", "authorization_date", "environment", "authorized_xml", "messages")
        if any(not hasattr(result, field) for field in required):
            raise SriAuthorizationProtocolError("Resultado de autorización inválido.")
        if result.access_key_consulted != document.access_key:
            raise SriAuthorizationProtocolError("La clave consultada no coincide.")
        if result.environment is not None and result.environment != document.environment:
            raise SriAuthorizationProtocolError("El ambiente retornado no coincide.")
        if result.outcome == SriAuthorizationAttemptStatus.AUTHORIZED:
            if not result.authorization_number or result.authorization_date is None or not result.authorized_xml:
                raise SriAuthorizationProtocolError("La autorización carece de evidencia oficial completa.")
            if timezone.is_naive(result.authorization_date):
                raise SriAuthorizationProtocolError("La fecha de autorización debe tener zona horaria.")
        elif result.outcome not in (SriAuthorizationAttemptStatus.NOT_AUTHORIZED, SriAuthorizationAttemptStatus.PENDING):
            raise SriAuthorizationProtocolError("Outcome de autorización desconocido.")

    @staticmethod
    def _finalize_result(document_id, attempt_id, result):
        with transaction.atomic():
            document = ElectronicDocument.objects.select_for_update().get(pk=document_id)
            attempt = SriAuthorizationAttempt.objects.select_for_update().get(pk=attempt_id, electronic_document_id=document_id)
            ElectronicDocumentAuthorizationService._validate_result(document, result)
            for message in result.messages or ():
                SriAuthorizationMessage.objects.create(
                    attempt=attempt,
                    message_type=message.message_type,
                    identifier=message.identifier,
                    message=message.message or "",
                    additional_information=message.additional_information,
                )
            attempt.finished_at = timezone.now()
            attempt.authorization_number = result.authorization_number
            attempt.authorization_date = result.authorization_date
            attempt.response_environment = result.environment
            if result.outcome == SriAuthorizationAttemptStatus.AUTHORIZED:
                document.status = SriDocumentStatus.AUTHORIZED
                document.authorization_number = result.authorization_number
                document.authorization_date = result.authorization_date
                document.authorized_xml = result.authorized_xml
                attempt.status = SriAuthorizationAttemptStatus.AUTHORIZED
            elif result.outcome == SriAuthorizationAttemptStatus.NOT_AUTHORIZED:
                document.status = SriDocumentStatus.REJECTED
                attempt.status = SriAuthorizationAttemptStatus.NOT_AUTHORIZED
            else:
                attempt.status = SriAuthorizationAttemptStatus.PENDING
            attempt.save()
            document.save(update_fields=["status", "authorization_number", "authorization_date", "authorized_xml", "updated_at"])
        return document

    @staticmethod
    def _finalize_error(document_id, attempt_id, status, error):
        with transaction.atomic():
            attempt = SriAuthorizationAttempt.objects.select_for_update().get(pk=attempt_id, electronic_document_id=document_id)
            if attempt.status == SriAuthorizationAttemptStatus.IN_PROGRESS:
                attempt.status = status
                attempt.finished_at = timezone.now()
                attempt.error_type = type(error).__name__
                attempt.error_message = str(error)
                attempt.save(update_fields=["status", "finished_at", "error_type", "error_message"])
