from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from django.test import TestCase

from lxml import etree

from signxml import SignatureConfiguration, XMLVerifier

from sri.constants.document_status import SriDocumentStatus
from sri.services.certificate_service import CertificateService
from sri.services.pkcs12_xml_signer import Pkcs12XmlSigner
from sri.services.xml_signing_service import XmlSigningService

from sri.tests.helpers import create_test_electronic_document


class XmlSigningIntegrationTest(TestCase):

    PASSWORD = "integration-test-password"

    @classmethod
    def setUpTestData(cls):

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        subject = issuer = x509.Name(
            [
                x509.NameAttribute(
                    NameOID.COUNTRY_NAME,
                    "EC",
                ),
                x509.NameAttribute(
                    NameOID.ORGANIZATION_NAME,
                    "Sisadmi Integration Test",
                ),
                x509.NameAttribute(
                    NameOID.COMMON_NAME,
                    "sisadmi.integration.test",
                ),
            ]
        )

        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(
                private_key.public_key()
            )
            .serial_number(
                x509.random_serial_number()
            )
            .not_valid_before(
                datetime.utcnow()
            )
            .not_valid_after(
                datetime.utcnow()
                + timedelta(days=365)
            )
            .add_extension(
                x509.BasicConstraints(
                    ca=False,
                    path_length=None,
                ),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=True,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(
                private_key,
                hashes.SHA256(),
            )
        )

        cls.p12_data = (
            pkcs12.serialize_key_and_certificates(
                name=b"sisadmi-integration-test",
                key=private_key,
                cert=certificate,
                cas=None,
                encryption_algorithm=(
                    serialization.BestAvailableEncryption(
                        cls.PASSWORD.encode("utf-8")
                    )
                ),
            )
        )

        cls.certificate = certificate

    def test_pkcs12_to_signed_electronic_document(self):

        # --------------------------------------------------
        # 1. Crear documento electrónico
        # --------------------------------------------------

        electronic_document = (
            create_test_electronic_document()
        )

        electronic_document.status = (
            SriDocumentStatus.GENERATED
        )

        electronic_document.xml = """
<factura id="comprobante">
    <datos>SISADMI INTEGRATION TEST</datos>
</factura>
""".strip()

        electronic_document.save(
            update_fields=[
                "status",
                "xml",
            ]
        )

        # --------------------------------------------------
        # 2. Cargar PKCS#12
        # --------------------------------------------------

        certificate_data = CertificateService.load(
            certificate_data=self.p12_data,
            password=self.PASSWORD,
        )

        self.assertIsNotNone(
            certificate_data.private_key
        )

        self.assertIsNotNone(
            certificate_data.certificate
        )

        # --------------------------------------------------
        # 3. Crear firmador XAdES
        # --------------------------------------------------

        signer = Pkcs12XmlSigner(
            certificate_data
        )

        # --------------------------------------------------
        # 4. Firmar mediante el servicio
        # --------------------------------------------------

        result = XmlSigningService.sign(
            electronic_document,
            signer,
        )

        result.refresh_from_db()

        # --------------------------------------------------
        # 5. Verificar estado
        # --------------------------------------------------

        self.assertEqual(
            result.status,
            SriDocumentStatus.SIGNED,
        )

        # --------------------------------------------------
        # 6. Verificar que existe XML
        # --------------------------------------------------

        self.assertTrue(
            result.xml
        )

        # --------------------------------------------------
        # 7. Verificar estructura XML
        # --------------------------------------------------

        signed_xml = etree.fromstring(
            result.xml.encode("UTF-8")
        )

        self.assertEqual(
            signed_xml.tag,
            "factura",
        )

        self.assertEqual(
            signed_xml.get("id"),
            "comprobante",
        )

        # --------------------------------------------------
        # 8. Verificar firma XAdES
        # --------------------------------------------------

        signature = signed_xml.find(
            ".//{http://www.w3.org/2000/09/xmldsig#}Signature"
        )

        self.assertIsNotNone(
            signature
        )

        # --------------------------------------------------
        # 9. Verificación criptográfica
        # --------------------------------------------------

        certificate_pem = (
            certificate_data.certificate.public_bytes(
                serialization.Encoding.PEM
            )
        )

        verification_result = XMLVerifier().verify(
            result.xml.encode("UTF-8"),
            x509_cert=certificate_pem,
            expect_config=SignatureConfiguration(
                expect_references=3
            ),
        )

        self.assertEqual(
            len(verification_result),
            3,
        )

        self.assertEqual(
            verification_result[0].signed_xml.tag,
            "factura",
        )
