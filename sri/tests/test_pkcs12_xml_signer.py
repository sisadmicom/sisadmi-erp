from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from django.test import SimpleTestCase

from lxml import etree

from signxml import (
    SignatureConfiguration,
    XMLVerifier,
)

from sri.services.certificate_service import CertificateData
from sri.services.pkcs12_xml_signer import Pkcs12XmlSigner
from sri.services.xml_signer import XmlSigner


class Pkcs12XmlSignerTest(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

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
                    "Sisadmi Test",
                ),
                x509.NameAttribute(
                    NameOID.COMMON_NAME,
                    "sisadmi.test",
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
            .sign(
                private_key,
                hashes.SHA256(),
            )
        )

        cls.certificate_data = CertificateData(
            private_key=private_key,
            certificate=certificate,
            additional_certificates=[],
        )

    def create_test_xml(self):

        return etree.fromstring(
            b"""
            <factura id="comprobante">
                <datos>SISADMI TEST</datos>
            </factura>
            """
        )

    def test_implements_xml_signer(self):

        signer = Pkcs12XmlSigner(
            self.certificate_data
        )

        self.assertIsInstance(
            signer,
            XmlSigner,
        )

    def test_stores_certificate_data(self):

        signer = Pkcs12XmlSigner(
            self.certificate_data
        )

        self.assertIs(
            signer.certificate_data,
            self.certificate_data,
        )

    def test_rejects_invalid_certificate_data(self):

        with self.assertRaisesMessage(
            TypeError,
            "certificate_data debe ser una instancia "
            "de CertificateData.",
        ):
            Pkcs12XmlSigner(
                certificate_data=None
            )

    def test_rejects_certificate_without_private_key(
        self,
    ):

        certificate_data = CertificateData(
            private_key=None,
            certificate=self.certificate_data.certificate,
            additional_certificates=[],
        )

        with self.assertRaisesMessage(
            ValueError,
            "El certificado no contiene una clave privada.",
        ):
            Pkcs12XmlSigner(
                certificate_data
            )

    def test_rejects_certificate_without_certificate(
        self,
    ):

        certificate_data = CertificateData(
            private_key=self.certificate_data.private_key,
            certificate=None,
            additional_certificates=[],
        )

        with self.assertRaisesMessage(
            ValueError,
            "El certificado no contiene un certificado.",
        ):
            Pkcs12XmlSigner(
                certificate_data
            )

    def test_sign_returns_signed_xml(self):

        signer = Pkcs12XmlSigner(
            self.certificate_data
        )

        signed_xml = signer.sign(
            self.create_test_xml()
        )

        self.assertIsInstance(
            signed_xml,
            str,
        )

        signed_xml_element = etree.fromstring(
            signed_xml.encode("UTF-8")
        )

        self.assertEqual(
            signed_xml_element.tag,
            "factura",
        )

    def test_sign_contains_xades_signature(self):

        signer = Pkcs12XmlSigner(
            self.certificate_data
        )

        signed_xml = signer.sign(
            self.create_test_xml()
        )

        signed_xml_element = etree.fromstring(
            signed_xml.encode("UTF-8")
        )

        signature = signed_xml_element.find(
            ".//{http://www.w3.org/2000/09/xmldsig#}Signature"
        )

        self.assertIsNotNone(
            signature
        )

    def test_sign_creates_three_references(self):

        signer = Pkcs12XmlSigner(
            self.certificate_data
        )

        signed_xml = signer.sign(
            self.create_test_xml()
        )

        signed_xml_element = etree.fromstring(
            signed_xml.encode("UTF-8")
        )

        references = signed_xml_element.findall(
            ".//{http://www.w3.org/2000/09/xmldsig#}Reference"
        )

        self.assertEqual(
            len(references),
            3,
        )

    def test_signed_xml_can_be_verified(self):

        signer = Pkcs12XmlSigner(
            self.certificate_data
        )

        signed_xml = signer.sign(
            self.create_test_xml()
        )

        signed_xml_data = signed_xml.encode(
            "UTF-8"
        )

        certificate_pem = (
            self.certificate_data.certificate.public_bytes(
                Encoding.PEM
            )
        )

        result = XMLVerifier().verify(
            signed_xml_data,
            x509_cert=certificate_pem,
            expect_config=SignatureConfiguration(
                expect_references=3
            ),
        )

        self.assertEqual(
            len(result),
            3,
        )

        self.assertEqual(
            result[0].signed_xml.tag,
            "factura",
        )