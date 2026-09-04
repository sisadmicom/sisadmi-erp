from datetime import datetime, timedelta
from xml.etree.ElementTree import fromstring

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.test import TestCase

from sri.constants.document_status import SriDocumentStatus
from sri.services.certificate_service import CertificateService
from sri.services.electronic_invoice_service import ElectronicInvoiceService
from sri.services.pkcs12_xml_signer import Pkcs12XmlSigner
from sri.services.test_xml_signer import TestXmlSigner
from sri.tests.helpers.invoice_factory import create_test_invoice_environment

from signxml import SignatureConfiguration, XMLVerifier

from unittest.mock import Mock, patch


class ElectronicInvoiceServiceTest(TestCase):

    def test_generate_invoice(self):

        data = create_test_invoice_environment()

        electronic_document = (
            ElectronicInvoiceService.generate(
                document=data["sale"],
                document_type="01",
                emission_point=data["emission_point"],
                environment=data["environment"],
                emission_type=data["emission_type"],
            )
        )

        electronic_document.refresh_from_db()

        self.assertEqual(
            electronic_document.status,
            SriDocumentStatus.GENERATED,
        )

        self.assertTrue(
            electronic_document.xml
        )

        root = fromstring(
            electronic_document.xml
        )

        self.assertEqual(
            root.tag,
            "factura",
        )

        self.assertEqual(
            root.get("id"),
            "comprobante",
        )

        self.assertIn(
            "Empresa Test",
            electronic_document.xml,
        )

        self.assertIn(
            "Cliente Test",
            electronic_document.xml,
        )

        self.assertIn(
            "000000025",
            electronic_document.xml,
        )

    def test_sign_invoice_with_fake_signer(self):

        data = create_test_invoice_environment()

        electronic_document = (
            ElectronicInvoiceService.generate(
                document=data["sale"],
                document_type="01",
                emission_point=data["emission_point"],
                environment=data["environment"],
                emission_type=data["emission_type"],
            )
        )

        self.assertEqual(
            electronic_document.status,
            SriDocumentStatus.GENERATED,
        )

        signer = TestXmlSigner()

        result = ElectronicInvoiceService.sign(
            electronic_document,
            signer,
        )

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            SriDocumentStatus.SIGNED,
        )

        self.assertTrue(
            result.xml
        )

        self.assertIn(
            "TEST-SIGNATURE",
            result.xml,
        )

    def test_sign_invoice_with_pkcs12_certificate(self):

        data = create_test_invoice_environment()

        electronic_document = (
            ElectronicInvoiceService.generate(
                document=data["sale"],
                document_type="01",
                emission_point=data["emission_point"],
                environment=data["environment"],
                emission_type=data["emission_type"],
            )
        )

        self.assertEqual(
            electronic_document.status,
            SriDocumentStatus.GENERATED,
        )

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
            .public_key(private_key.public_key())
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

        password = "integration-password"

        p12_data = (
            pkcs12.serialize_key_and_certificates(
                name=b"sisadmi-integration",
                key=private_key,
                cert=certificate,
                cas=None,
                encryption_algorithm=(
                    serialization.BestAvailableEncryption(
                        password.encode("utf-8")
                    )
                ),
            )
        )

        certificate_data = CertificateService.load(
            certificate_data=p12_data,
            password=password,
        )

        self.assertIsNotNone(
            certificate_data.private_key
        )

        self.assertIsNotNone(
            certificate_data.certificate
        )

        signer = Pkcs12XmlSigner(
            certificate_data
        )

        result = ElectronicInvoiceService.sign(
            electronic_document,
            signer,
        )

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            SriDocumentStatus.SIGNED,
        )

        self.assertTrue(
            result.xml
        )

        self.assertIn(
            "<ds:Signature",
            result.xml,
        )

        self.assertIn(
            "QualifyingProperties",
            result.xml,
        )

        self.assertIn(
            "SignedProperties",
            result.xml,
        )

        verified = XMLVerifier().verify(
            result.xml.encode("utf-8"),
            x509_cert=certificate.public_bytes(
                serialization.Encoding.PEM
            ),
            expect_config=SignatureConfiguration(
                expect_references=3
            ),
        )

        self.assertTrue(
            verified
        )

    def test_sign_rejects_document_not_generated(self):

        data = create_test_invoice_environment()

        electronic_document = (
            ElectronicInvoiceService.generate(
                document=data["sale"],
                document_type="01",
                emission_point=data["emission_point"],
                environment=data["environment"],
                emission_type=data["emission_type"],
            )
        )

        electronic_document.status = (
            SriDocumentStatus.DRAFT
        )
        electronic_document.save(
            update_fields=["status"]
        )

        signer = TestXmlSigner()

        with self.assertRaises(ValueError):

            ElectronicInvoiceService.sign(
                electronic_document,
                signer,
            )

    def test_sign_for_company_uses_signer_factory(self):

        electronic_document = Mock()
        electronic_document.company = Mock()

        signer = Mock()

        signer_factory = Mock()
        signer_factory.create_for_company.return_value = signer

        with patch(
            "sri.services.electronic_invoice_service."
            "XmlSigningService.sign"
        ) as sign_mock:

            sign_mock.return_value = electronic_document

            result = ElectronicInvoiceService.sign_for_company(
                electronic_document,
                signer_factory,
            )

        signer_factory.create_for_company.assert_called_once_with(
            electronic_document.company
        )

        sign_mock.assert_called_once_with(
            electronic_document,
            signer,
        )

        self.assertIs(
            result,
            electronic_document,
        )


    def test_sign_for_company_propagates_factory_error(self):

        electronic_document = Mock()
        electronic_document.company = Mock()

        signer_factory = Mock()

        signer_factory.create_for_company.side_effect = ValueError(
            "La empresa no tiene un certificado SRI "
            "activo y predeterminado."
        )

        with self.assertRaisesMessage(
            ValueError,
            "La empresa no tiene un certificado SRI "
            "activo y predeterminado.",
        ):

            ElectronicInvoiceService.sign_for_company(
                electronic_document,
                signer_factory,
            )