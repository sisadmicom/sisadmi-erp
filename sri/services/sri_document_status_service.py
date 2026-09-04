from django.utils import timezone

from sri.constants.document_status import SriDocumentStatus


class SriDocumentStatusService:
    """
    Servicio encargado de manejar las transiciones
    de estado de documentos electrónicos SRI.
    """

    ALLOWED_TRANSITIONS = {

        SriDocumentStatus.DRAFT: [
            SriDocumentStatus.GENERATED,
            SriDocumentStatus.ERROR,
        ],

        SriDocumentStatus.GENERATED: [
            SriDocumentStatus.SIGNED,
            SriDocumentStatus.ERROR,
        ],

        SriDocumentStatus.SIGNED: [
            SriDocumentStatus.SENT,
            SriDocumentStatus.ERROR,
        ],

        SriDocumentStatus.SENT: [
            SriDocumentStatus.RECEIVED,
            SriDocumentStatus.AUTHORIZED,
            SriDocumentStatus.REJECTED,
            SriDocumentStatus.ERROR,
        ],

        SriDocumentStatus.RECEIVED: [
            SriDocumentStatus.AUTHORIZED,
            SriDocumentStatus.REJECTED,
            SriDocumentStatus.ERROR,
        ],

        SriDocumentStatus.AUTHORIZED: [],

        SriDocumentStatus.REJECTED: [],

        SriDocumentStatus.ERROR: [
            SriDocumentStatus.DRAFT,
        ],
    }


    @staticmethod
    def change_status(
        electronic_document,
        new_status,
    ):
        """
        Cambia el estado del documento electrónico
        validando la transición.
        """

        current_status = electronic_document.status

        if current_status == new_status:
            return electronic_document


        allowed = (
            SriDocumentStatusService
            .ALLOWED_TRANSITIONS
            .get(current_status, [])
        )


        if new_status not in allowed:
            raise ValueError(
                f"Transición no permitida: "
                f"{current_status} -> {new_status}"
            )


        electronic_document.status = new_status


        if new_status == SriDocumentStatus.SENT:
            electronic_document.sent_at = timezone.now()


        if new_status == SriDocumentStatus.AUTHORIZED:
            electronic_document.authorization_date = timezone.now()


        electronic_document.save()


        return electronic_document
