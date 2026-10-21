from django.db import transaction

from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument
from sri.services.invoice_validation import (
    FiscalValidationError, SIGNING_ERROR, company_signer, validate_document_invoice,
)
from sri.services.xml_signing_service import XmlSigningService


class ElectronicDocumentSigningService:
    """Resolve the company's existing PKCS#12 and use the verified signing path."""

    @staticmethod
    def sign(*, electronic_document):
        if not isinstance(electronic_document, ElectronicDocument) or not electronic_document.pk:
            raise FiscalValidationError("El documento electrónico debe estar persistido.")
        source_xml = None
        try:
            with transaction.atomic():
                locked = ElectronicDocument.objects.select_for_update().get(pk=electronic_document.pk)
                if locked.status != SriDocumentStatus.GENERATED:
                    raise FiscalValidationError("Solo se pueden firmar documentos con XML generado.")
                source_xml = locked.xml
                validate_document_invoice(locked)
                signer = ElectronicDocumentSigningService._resolve_signer(locked)
                return XmlSigningService.sign(locked, signer, certificate=signer.certificate_data.certificate)
        except Exception as error:
            if source_xml is not None:
                XmlSigningService._register_error(electronic_document.pk, source_xml)
            if isinstance(error, FiscalValidationError):
                raise
            raise FiscalValidationError(SIGNING_ERROR) from None

    @staticmethod
    def _resolve_signer(electronic_document):
        return company_signer(electronic_document.company)
