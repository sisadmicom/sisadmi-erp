from django.db import transaction

from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument, SriCertificate
from sri.services.certificate_service import CertificateService
from sri.services.environment_secret_provider import EnvironmentSecretProvider
from sri.services.pkcs12_xml_signer import Pkcs12XmlSigner
from sri.services.sri_document_status_service import SriDocumentStatusService


class ElectronicDocumentSigningService:
    """Sign a generated electronic document with its company certificate."""

    @staticmethod
    @transaction.atomic
    def sign(*, electronic_document):
        if not isinstance(electronic_document, ElectronicDocument):
            raise ValueError("El documento electrónico no es válido.")
        if not electronic_document.pk:
            raise ValueError("El documento electrónico debe estar persistido.")

        try:
            locked = (
                ElectronicDocument.objects
                .select_for_update()
                .get(pk=electronic_document.pk)
            )
        except ElectronicDocument.DoesNotExist as error:
            raise ValueError("El documento electrónico no existe.") from error

        if locked.status != SriDocumentStatus.GENERATED:
            raise ValueError(
                "Solo se pueden firmar documentos con XML generado."
            )
        if not locked.xml:
            raise ValueError(
                "El documento electrónico no tiene XML para firmar."
            )

        signer = ElectronicDocumentSigningService._resolve_signer(locked)
        source_xml = locked.xml
        signed_xml = signer.sign(source_xml)
        if not signed_xml:
            raise ValueError("El proceso de firma no devolvió XML.")

        locked.xml = signed_xml
        locked.save(update_fields=["xml"])
        SriDocumentStatusService.change_status(
            locked,
            SriDocumentStatus.SIGNED,
        )
        return locked

    @staticmethod
    def _resolve_signer(electronic_document):
        certificates = SriCertificate.objects.filter(
            company_id=electronic_document.company_id,
            is_active=True,
            is_default=True,
        )
        try:
            certificate = certificates.get()
        except SriCertificate.DoesNotExist as error:
            raise ValueError(
                "La empresa no tiene un certificado SRI activo y predeterminado."
            ) from error
        except SriCertificate.MultipleObjectsReturned as error:
            raise ValueError(
                "La empresa tiene múltiples certificados SRI activos y predeterminados."
            ) from error

        if not certificate.certificate_file:
            raise ValueError(
                "El certificado SRI no tiene un archivo PKCS#12 configurado."
            )

        secret_provider = EnvironmentSecretProvider()
        password = secret_provider.get(certificate.secret_key)
        with certificate.certificate_file.open("rb") as certificate_file:
            pkcs12_data = certificate_file.read()

        certificate_data = CertificateService.load(
            pkcs12_data,
            password,
        )
        CertificateService.validate_certificate(certificate_data.certificate)
        return Pkcs12XmlSigner(certificate_data)
