from django.db import transaction

from sri.constants.document_status import SriDocumentStatus
from sri.services.sri_document_status_service import (
    SriDocumentStatusService,
)


class XmlSigningService:
    """
    Servicio responsable del proceso de firma electrónica.

    El servicio no conoce la implementación criptográfica.

    El objeto signer solamente debe proporcionar:

        sign(xml)

    Puede ser:
    - un firmador real
    - un firmador de pruebas
    - un mock
    - una implementación futura con certificado .p12
    """

    @staticmethod
    def sign(
        electronic_document,
        signer,
    ):

        # --------------------------------------------------
        # 1. Validar estado
        # --------------------------------------------------

        if (
            electronic_document.status
            != SriDocumentStatus.GENERATED
        ):
            raise ValueError(
                "Solo se pueden firmar documentos "
                "con XML generado."
            )

        # --------------------------------------------------
        # 2. Validar XML
        # --------------------------------------------------

        if not electronic_document.xml:
            raise ValueError(
                "El documento electrónico no tiene XML "
                "para firmar."
            )

        # --------------------------------------------------
        # 3. Validar interfaz del firmador
        # --------------------------------------------------

        if not hasattr(signer, "sign"):

            raise TypeError(
                "El firmador debe proporcionar "
                "un método sign(xml)."
            )

        # --------------------------------------------------
        # 4. Ejecutar firma
        # --------------------------------------------------

        try:

            signed_xml = signer.sign(
                electronic_document.xml
            )

        except Exception as error:

            XmlSigningService._register_error(
                electronic_document,
                error,
            )

            raise

        # --------------------------------------------------
        # 5. Validar resultado
        # --------------------------------------------------

        if not signed_xml:

            error = ValueError(
                "El proceso de firma no devolvió XML."
            )

            XmlSigningService._register_error(
                electronic_document,
                error,
            )

            raise error

        # --------------------------------------------------
        # 6. Guardar XML firmado
        # --------------------------------------------------

        electronic_document.xml = signed_xml

        electronic_document.save(
            update_fields=[
                "xml",
            ]
        )

        # --------------------------------------------------
        # 7. Cambiar estado
        # --------------------------------------------------

        SriDocumentStatusService.change_status(
            electronic_document,
            SriDocumentStatus.SIGNED,
        )

        return electronic_document

    @staticmethod
    @transaction.atomic
    def _register_error(
        electronic_document,
        error,
    ):
        """
        Registra el error en una transacción independiente.
        """

        electronic_document.refresh_from_db()

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
