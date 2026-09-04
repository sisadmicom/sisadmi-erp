from django.db import transaction

from sri.constants.document_status import SriDocumentStatus

from sri.services.xml_generator_service import XmlGeneratorService
from sri.services.sri_document_status_service import (
    SriDocumentStatusService,
)


class XmlGenerationService:
    """
    Servicio encargado de generar y almacenar
    el XML de un documento electrónico SRI.
    """

    @staticmethod
    @transaction.atomic
    def generate(
        electronic_document,
    ):

        try:

            xml = XmlGeneratorService.generate_invoice(
                electronic_document
            )

            electronic_document.xml = xml

            electronic_document.save(
                update_fields=[
                    "xml",
                ]
            )


            SriDocumentStatusService.change_status(
                electronic_document,
                SriDocumentStatus.GENERATED,
            )


            return electronic_document


        except Exception as error:

            electronic_document.error_message = str(
                error
            )

            electronic_document.status = (
                SriDocumentStatus.ERROR
            )

            electronic_document.save(
                update_fields=[
                    "status",
                    "error_message",
                ]
            )

            raise
