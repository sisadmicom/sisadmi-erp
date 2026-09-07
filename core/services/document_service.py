#core/services/document_service.py
from django.db import transaction
from django.utils import timezone

from core.constants.document_status import DocumentStatus
from core.services.document_validator import DocumentValidator
from core.services.document_totals_service import DocumentTotalsService
from core.services.sequence_service import SequenceService


class DocumentService:

    @staticmethod
    @transaction.atomic
    def confirm(document, user=None):

        DocumentValidator.validate(document)

        if (
                hasattr(document, "subtotal")
                and hasattr(document, "tax")
                and hasattr(document, "total")
            ):
             DocumentTotalsService.calculate(document)
        
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

        if document.is_cancelled():
            raise ValueError(
                "El documento ya fue anulado."
            )

        if not document.is_confirmed():
            raise ValueError(
                "Solo se pueden anular documentos confirmados."
            )

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