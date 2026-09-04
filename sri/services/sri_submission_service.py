from django.db import transaction

from sri.constants.document_status import SriDocumentStatus
from sri.services.sri_document_status_service import (
    SriDocumentStatusService,
)
from sri.services.xml_validation_service import (
    XmlValidationService,
)


class SriSubmissionService:
    """
    Servicio responsable de enviar un documento electrónico
    firmado al SRI.

    Flujo normal:

        SIGNED
           ↓
        validar XML
           ↓
        enviar al SRI
           ↓
        SENT

    Si existe un error de comunicación:

        SIGNED
           ↓
        ERROR
    """

    @staticmethod
    def submit(
        electronic_document,
        client,
    ):

        # --------------------------------------------------
        # 1. El documento debe estar firmado
        # --------------------------------------------------

        if (
            electronic_document.status
            != SriDocumentStatus.SIGNED
        ):
            raise ValueError(
                "Solo se pueden enviar al SRI "
                "documentos firmados."
            )

        # --------------------------------------------------
        # 2. Debe existir XML
        # --------------------------------------------------

        if not electronic_document.xml:

            raise ValueError(
                "El documento electrónico no tiene XML."
            )

        # --------------------------------------------------
        # 3. Validar XML
        # --------------------------------------------------

        XmlValidationService.validate(
            electronic_document.xml
        )

        # --------------------------------------------------
        # 4. Intentar comunicación con SRI
        # --------------------------------------------------

        try:

            response = client.send(
                xml=electronic_document.xml,
                environment=(
                    electronic_document.environment
                ),
            )

        except Exception as error:

            SriSubmissionService._register_error(
                electronic_document,
                error,
            )

            raise

        # --------------------------------------------------
        # 5. Marcar como enviado
        # --------------------------------------------------

        SriDocumentStatusService.change_status(
            electronic_document,
            SriDocumentStatus.SENT,
        )

        return response

    @staticmethod
    @transaction.atomic
    def _register_error(
        electronic_document,
        error,
    ):
        """
        Registra un error de comunicación con el SRI.

        Esta operación se ejecuta en una transacción propia.
        """

        electronic_document.error_message = str(
            error
        )

        electronic_document.save(
            update_fields=[
                "error_message",
            ]
        )

        SriDocumentStatusService.change_status(
            electronic_document,
            SriDocumentStatus.ERROR,
        )
