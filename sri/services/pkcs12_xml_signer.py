from lxml import etree
from signxml.xades import XAdESSigner

from sri.services.certificate_service import CertificateData
from sri.services.xml_signer import XmlSigner


class Pkcs12XmlSigner(XmlSigner):
    """
    Firmador XAdES basado en un certificado PKCS#12.

    Responsabilidades:
    - Recibir los datos del certificado.
    - Convertir el XML de texto a lxml.
    - Aplicar la firma XAdES.
    - Devolver el XML firmado como texto.

    El servicio no conoce el modelo ElectronicDocument.
    """

    DEFAULT_REFERENCE_ID = "comprobante"

    def __init__(self, certificate_data):

        if not isinstance(
            certificate_data,
            CertificateData,
        ):
            raise TypeError(
                "certificate_data debe ser una instancia "
                "de CertificateData."
            )

        if certificate_data.private_key is None:
            raise ValueError(
                "El certificado no contiene una clave privada."
            )

        if certificate_data.certificate is None:
            raise ValueError(
                "El certificado no contiene un certificado."
            )

        self.certificate_data = certificate_data

    def _to_lxml(self, xml):
        """
        Convierte el XML recibido a un elemento lxml.
        """

        if isinstance(xml, etree._Element):
            return xml

        if isinstance(xml, bytes):
            return etree.fromstring(xml)

        if isinstance(xml, str):
            return etree.fromstring(
                xml.encode("UTF-8")
            )

        raise TypeError(
            "El XML debe ser str, bytes o "
            "lxml.etree._Element."
        )

    def _get_reference_uri(self, xml):
        """
        Obtiene el URI del elemento que será firmado.

        Si el elemento raíz tiene atributo id,
        se utiliza dicho identificador.

        Caso contrario se utiliza #comprobante.
        """

        root_id = xml.get("id")

        if root_id:
            return f"#{root_id}"

        return f"#{self.DEFAULT_REFERENCE_ID}"

    def sign(self, xml):
        """
        Firma el XML utilizando XAdES y devuelve
        el XML firmado como texto UTF-8.
        """

        xml = self._to_lxml(xml)

        reference_uri = self._get_reference_uri(
            xml
        )

        signer = XAdESSigner()

        certificates = [
            self.certificate_data.certificate
        ]

        certificates.extend(
            self.certificate_data.additional_certificates
        )

        signed_xml = signer.sign(
            xml,
            key=self.certificate_data.private_key,
            cert=certificates,
            reference_uri=reference_uri,
        )

        return etree.tostring(
            signed_xml,
            xml_declaration=True,
            encoding="UTF-8",
        ).decode("UTF-8")