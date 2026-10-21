from django.db import transaction

from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument
from sri.services.invoice_validation import (
    FiscalValidationError, SIGNING_ERROR, validate_document_invoice, verify_signed_invoice, company_signer,
)
from sri.services.sri_document_status_service import SriDocumentStatusService


class XmlSigningService:
    """Sign and verify the exact persisted invoice; failures keep GENERATED."""

    @staticmethod
    def sign(electronic_document, signer, *, certificate=None):
        locked = None
        source_xml = None
        try:
            with transaction.atomic():
                locked = ElectronicDocument.objects.select_for_update().get(pk=electronic_document.pk)
                if locked.status != SriDocumentStatus.GENERATED:
                    raise FiscalValidationError("Solo se pueden firmar documentos con XML generado.")
                source_xml = locked.xml
                if not source_xml:
                    raise FiscalValidationError("El documento electrónico no tiene XML para firmar.")
                validate_document_invoice(locked)
                expected_certificate = certificate
                if expected_certificate is None:
                    expected_certificate = company_signer(locked.company).certificate_data.certificate
                signed_xml = signer.sign(source_xml)
                verify_signed_invoice(signed_xml, certificate=expected_certificate,
                                      source_xml=source_xml)
                locked.xml = signed_xml
                locked.error_message = ""
                locked.save(update_fields=["xml", "error_message"])
                SriDocumentStatusService.change_status(locked, SriDocumentStatus.SIGNED)
                return locked
        except Exception as error:
            if locked is not None and source_xml is not None:
                XmlSigningService._register_error(locked.pk, source_xml)
            if isinstance(error, FiscalValidationError):
                raise
            raise FiscalValidationError(SIGNING_ERROR) from None

    @staticmethod
    def _register_error(document_id, source_xml):
        # Conditional update does not overwrite a concurrently signed/edited
        # version. No raw certificate/transport exception is persisted.
        ElectronicDocument.objects.filter(
            pk=document_id, status=SriDocumentStatus.GENERATED, xml=source_xml,
        ).update(error_message=SIGNING_ERROR)
