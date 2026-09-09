#core/services/document_service.py
from django.db import transaction
from django.utils import timezone

from core.constants.document_status import DocumentStatus
from core.services.sequence_service import SequenceService


class DocumentService:

    @staticmethod
    def ensure_can_confirm(document):
        """Valida el estado para confirmar sin mutar el documento."""
        if not document.is_draft():
            raise ValueError(
                "Solo se pueden confirmar documentos en borrador."
            )

    @staticmethod
    def ensure_can_cancel(document):
        """Valida el estado para anular sin mutar el documento."""
        if document.is_cancelled():
            raise ValueError(
                "El documento ya fue anulado."
            )

        if not document.is_confirmed():
            raise ValueError(
                "Solo se pueden anular documentos confirmados."
            )

    @staticmethod
    @transaction.atomic
    def confirm(document, user=None):

        DocumentService.ensure_can_confirm(document)

        document.number = SequenceService.next_number(
            company=document.company,
            branch=document.branch,
            document_type=document.document_type,
        )

        document.status = DocumentStatus.CONFIRMED
        document.confirmed_at = timezone.now()
        document.confirmed_by = user

        document.save(
            update_fields=[
                "number",
                "status",
                "confirmed_at",
                "confirmed_by",
                "updated_at",
            ]
        )

        document.refresh_from_db()

        return document

    @staticmethod
    @transaction.atomic
    def cancel(document, user=None):

        DocumentService.ensure_can_cancel(document)

        document.status = DocumentStatus.CANCELLED
        document.cancelled_at = timezone.now()
        document.cancelled_by = user

        document.save(
            update_fields=[
                "status",
                "cancelled_at",
                "cancelled_by",
                "updated_at",
            ]
        )

        document.refresh_from_db()

        return document