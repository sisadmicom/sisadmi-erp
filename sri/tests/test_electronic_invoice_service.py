from xml.etree.ElementTree import fromstring

from django.test import TestCase

from sri.constants.document_status import SriDocumentStatus
from sri.services.electronic_invoice_service import ElectronicInvoiceService
from sri.services.test_xml_signer import TestXmlSigner
from sri.tests.helpers.invoice_factory import create_test_invoice_environment


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

        self.assertEqual(
            root.findtext("infoTributaria/secuencial"),
            "000000001",
        )

    def generated_with_certificate(self):
        from sri.tests.electronic_document_signing_test_support import create_certificate_record
        from sri.services.invoice_validation import company_signer
        import os

        data = create_test_invoice_environment()
        document = ElectronicInvoiceService.generate(
            document=data["sale"], document_type="01",
            emission_point=data["emission_point"], environment=data["environment"],
            emission_type=data["emission_type"],
        )
        record, _, certificate = create_certificate_record(data["company"])
        self.addCleanup(os.environ.pop, record.secret_key, None)
        return document, company_signer(data["company"]), certificate

    def test_fake_signature_is_rejected_with_company_certificate_configured(self):
        from sri.services.invoice_validation import FiscalValidationError

        document, _, _ = self.generated_with_certificate()
        original_xml = document.xml
        with self.assertRaisesMessage(FiscalValidationError, "XML fiscal inválido"):
            ElectronicInvoiceService.sign(document, TestXmlSigner())
        document.refresh_from_db()
        self.assertEqual(document.status, SriDocumentStatus.GENERATED)
        self.assertEqual(document.xml, original_xml)

    def test_sign_invoice_with_pkcs12_certificate(self):
        from sri.services.invoice_validation import verify_signed_invoice

        document, signer, certificate = self.generated_with_certificate()
        original_xml = document.xml
        result = ElectronicInvoiceService.sign(document, signer)
        result.refresh_from_db()
        self.assertEqual(result.status, SriDocumentStatus.SIGNED)
        self.assertEqual(result.error_message, "")
        self.assertTrue(result.xml)
        self.assertIn("<ds:Signature", result.xml)
        self.assertIn("QualifyingProperties", result.xml)
        self.assertIn("SignedProperties", result.xml)
        verify_signed_invoice(result.xml, certificate=certificate, source_xml=original_xml)

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
