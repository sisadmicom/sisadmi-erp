from sri.models import SriCertificate
from sri.services.pkcs12_xml_signer import Pkcs12XmlSigner


class SriSignerFactory:
    """
    Resuelve el certificado SRI de una empresa
    y construye el XmlSigner correspondiente.
    """

    def __init__(
        self,
        *,
        secret_provider,
        certificate_service,
    ):
        self.secret_provider = secret_provider
        self.certificate_service = certificate_service

    def get_certificate(self, company):
        """
        Devuelve el certificado activo y predeterminado
        de una empresa.
        """

        certificate = (
            SriCertificate.objects
            .filter(
                company=company,
                is_active=True,
                is_default=True,
            )
            .first()
        )

        if certificate is None:
            raise ValueError(
                "La empresa no tiene un certificado SRI "
                "activo y predeterminado."
            )

        return certificate

    def create_for_company(self, company):
        """
        Construye un Pkcs12XmlSigner listo para firmar.
        """

        certificate = self.get_certificate(
            company
        )

        if not certificate.certificate_file:
            raise ValueError(
                "El certificado SRI no tiene un archivo "
                "PKCS#12 configurado."
            )

        password = self.secret_provider.get(
            certificate.secret_key
        )

        with certificate.certificate_file.open(
            "rb"
        ) as certificate_file:
            pkcs12_data = certificate_file.read()

        certificate_data = (
            self.certificate_service.load(
                pkcs12_data,
                password,
            )
        )

        return Pkcs12XmlSigner(
            certificate_data
        )
