from django.db import transaction

from sri.services.electronic_document_service import (
    ElectronicDocumentService,
)

from sri.services.xml_generation_service import (
    XmlGenerationService,
)

from sri.services.xml_signing_service import (
    XmlSigningService,
)

from sri.services.xml_validation_service import (
    XmlValidationService,
)


class ElectronicInvoiceService:
    """
    Orquestador del proceso de facturación electrónica.

    Responsabilidades:

    - Crear el ElectronicDocument.
    - Generar el XML.
    - Validar el XML.
    - Firmar electrónicamente el XML.

    No conoce los detalles criptográficos de la firma.
    """

    @staticmethod
    @transaction.atomic
    def generate(
        document,
        document_type,
        emission_point,
        environment,
        emission_type,
    ):
        """
        Genera el documento electrónico y su XML.

        Flujo:

            Documento ERP confirmado
                    ↓
            ElectronicDocument
                    ↓
            XML generado
                    ↓
            XML validado
                    ↓
                 GENERATED

        Retorna el ElectronicDocument.
        """

        # --------------------------------------------------
        # 1. Crear documento electrónico
        # --------------------------------------------------

        electronic_document = (
            ElectronicDocumentService.create(
                document=document,
                document_type=document_type,
                emission_point=emission_point,
                environment=environment,
                emission_type=emission_type,
            )
        )

        # --------------------------------------------------
        # 2. Generar XML
        # --------------------------------------------------

        electronic_document = (
            XmlGenerationService.generate(
                electronic_document
            )
        )

        # --------------------------------------------------
        # 3. Validar XML
        # --------------------------------------------------

        XmlValidationService.validate(
            electronic_document.xml
        )

        # --------------------------------------------------
        # 4. Retornar documento
        # --------------------------------------------------

        return electronic_document

    @staticmethod
    @transaction.atomic
    def sign(
        electronic_document,
        signer,
    ):
        """
        Firma electrónicamente un documento generado.

        Flujo:

            GENERATED
                ↓
            XmlSigningService
                ↓
            XmlSigner
                ↓
            XML XAdES firmado
                ↓
              SIGNED

        El signer puede ser:

        - Pkcs12XmlSigner
        - un firmador de pruebas
        - un mock
        - otra implementación de XmlSigner
        """

        return XmlSigningService.sign(
            electronic_document,
            signer,
        )
    @staticmethod
    @transaction.atomic
    def sign_for_company(
        electronic_document,
        signer_factory,
    ):
        """
        Firma un documento electrónico utilizando
        el certificado configurado para su empresa.

        El signer_factory es responsable de resolver
        el certificado y construir el XmlSigner.
        """

        signer = signer_factory.create_for_company(
            electronic_document.company
        )

        return XmlSigningService.sign(
            electronic_document,
            signer,
        )