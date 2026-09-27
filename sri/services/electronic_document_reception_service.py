from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.constants.sri import SriEnvironment
from sri.constants.document_status import SriDocumentStatus
from sri.constants.reception_attempt_status import SriReceptionAttemptStatus
from sri.models.electronic_document import ElectronicDocument
from sri.models.sri_reception_attempt import SriReceptionAttempt
from sri.models.sri_reception_message import SriReceptionMessage
from sri.services.xml_validation_service import XmlValidationService


@dataclass(frozen=True)
class SriReceptionMessageData:
    message_type: str | None
    identifier: str | None
    message: str
    additional_information: str | None


@dataclass(frozen=True)
class SriReceptionResult:
    outcome: str
    messages: tuple[SriReceptionMessageData, ...] = ()


class ElectronicDocumentReceptionService:
    @staticmethod
    def submit(*, electronic_document, adapter):
        if not isinstance(electronic_document, ElectronicDocument) or not electronic_document.pk:
            raise ValueError("Se requiere un ElectronicDocument persistido.")
        with transaction.atomic():
            locked = ElectronicDocument.objects.select_for_update().get(pk=electronic_document.pk)
            source_xml, environment = ElectronicDocumentReceptionService._preflight(locked)
            if SriReceptionAttempt.objects.filter(electronic_document=locked, status__in=[SriReceptionAttemptStatus.IN_PROGRESS, SriReceptionAttemptStatus.UNCERTAIN]).exists():
                raise ValueError("El documento ya tiene una recepción activa o incierta.")
            try:
                attempt = SriReceptionAttempt.objects.create(electronic_document=locked, status=SriReceptionAttemptStatus.IN_PROGRESS)
            except IntegrityError as exc:
                raise ValueError("El documento ya tiene una recepción activa o incierta.") from exc
        try:
            result = ElectronicDocumentReceptionService._receive(adapter, source_xml, environment)
        except Exception as exc:
            ElectronicDocumentReceptionService._finalize_uncertain(electronic_document.pk, attempt.pk, exc)
            raise
        outcome = getattr(result, "outcome", None)
        if outcome == SriReceptionAttemptStatus.RECEIVED:
            return ElectronicDocumentReceptionService._finalize_terminal(electronic_document.pk, attempt.pk, SriReceptionAttemptStatus.RECEIVED, getattr(result, "messages", ()), SriDocumentStatus.RECEIVED)
        if outcome == SriReceptionAttemptStatus.REJECTED:
            return ElectronicDocumentReceptionService._finalize_terminal(electronic_document.pk, attempt.pk, SriReceptionAttemptStatus.REJECTED, getattr(result, "messages", ()), SriDocumentStatus.REJECTED)
        return ElectronicDocumentReceptionService._finalize_uncertain(electronic_document.pk, attempt.pk, ValueError("Respuesta de recepción desconocida."), propagate=False)

    @staticmethod
    def _receive(adapter, source_xml, environment):
        return adapter.receive(xml=source_xml, environment=environment)

    @staticmethod
    def _preflight(document):
        if document.status != SriDocumentStatus.SIGNED:
            raise ValueError("Solo se pueden recibir documentos firmados.")
        if not document.xml:
            raise ValueError("El documento electrónico no tiene XML.")
        if document.environment not in {value for value, _ in SriEnvironment.CHOICES}:
            raise ValueError("El ambiente SRI no es válido.")
        XmlValidationService.validate(document.xml)
        return document.xml, document.environment

    @staticmethod
    def _finalize_uncertain(document_id, attempt_id, error, propagate=True):
        with transaction.atomic():
            attempt = SriReceptionAttempt.objects.select_for_update().get(pk=attempt_id, electronic_document_id=document_id)
            if attempt.status == SriReceptionAttemptStatus.IN_PROGRESS:
                attempt.status = SriReceptionAttemptStatus.UNCERTAIN
                attempt.completed_at = timezone.now()
                attempt.error_type = type(error).__name__
                attempt.error_message = str(error)
                attempt.save(update_fields=["status", "completed_at", "error_type", "error_message"])
            document = ElectronicDocument.objects.get(pk=document_id)
        if propagate:
            raise error
        return document

    @staticmethod
    def _finalize_terminal(document_id, attempt_id, attempt_status, messages, document_status):
        with transaction.atomic():
            document = ElectronicDocument.objects.select_for_update().get(pk=document_id)
            attempt = SriReceptionAttempt.objects.select_for_update().get(pk=attempt_id, electronic_document_id=document_id)
            if attempt.status != SriReceptionAttemptStatus.IN_PROGRESS or document.status != SriDocumentStatus.SIGNED:
                raise ValueError("El intento de recepción ya no puede finalizarse.")
            for data in messages or ():
                SriReceptionMessage.objects.create(attempt=attempt, message_type=getattr(data, "message_type", None), identifier=getattr(data, "identifier", None), message=getattr(data, "message", ""), additional_information=getattr(data, "additional_information", None))
            attempt.status = attempt_status
            attempt.completed_at = timezone.now()
            attempt.save(update_fields=["status", "completed_at"])
            document.status = document_status
            document.save(update_fields=["status", "updated_at"])
        return document
