from django.test import TestCase

from sri.constants.document_status import SriDocumentStatus
from sri.services.xml_signing_service import (
    XmlSigningService,
)

from sri.tests.helpers import (
    create_test_electronic_document,
)


class FakeSigner:

    def sign(self, xml):

        return (
            xml.replace(
                "<factura>",
                '<factura firma="FAKE-SIGNATURE">',
            )
        )


class FailingSigner:

    def sign(self, xml):

        raise RuntimeError(
            "Error simulado de certificado."
        )


class XmlSigningServiceTest(TestCase):

    def test_sign_generated_document(self):

        electronic_document = (
            create_test_electronic_document()
        )

        electronic_document.status = (
            SriDocumentStatus.GENERATED
        )

        electronic_document.xml = (
            "<factura></factura>"
        )

        electronic_document.save(
            update_fields=[
                "status",
                "xml",
            ]
        )

        result = XmlSigningService.sign(
            electronic_document,
            FakeSigner(),
        )

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            SriDocumentStatus.SIGNED,
        )

        self.assertIn(
            "FAKE-SIGNATURE",
            result.xml,
        )

    def test_rejects_document_without_xml(self):

        electronic_document = (
            create_test_electronic_document()
        )

        electronic_document.status = (
            SriDocumentStatus.GENERATED
        )

        electronic_document.xml = None

        electronic_document.save(
            update_fields=[
                "status",
                "xml",
            ]
        )

        with self.assertRaisesMessage(
            ValueError,
            "El documento electrónico no tiene XML "
            "para firmar.",
        ):

            XmlSigningService.sign(
                electronic_document,
                FakeSigner(),
            )

    def test_rejects_non_generated_document(self):

        electronic_document = (
            create_test_electronic_document()
        )

        with self.assertRaisesMessage(
            ValueError,
            "Solo se pueden firmar documentos "
            "con XML generado.",
        ):

            XmlSigningService.sign(
                electronic_document,
                FakeSigner(),
            )

    def test_changes_status_to_error_when_signer_fails(
        self,
    ):

        electronic_document = (
            create_test_electronic_document()
        )

        electronic_document.status = (
            SriDocumentStatus.GENERATED
        )

        electronic_document.xml = (
            "<factura></factura>"
        )

        electronic_document.save(
            update_fields=[
                "status",
                "xml",
            ]
        )

        with self.assertRaisesMessage(
            RuntimeError,
            "Error simulado de certificado.",
        ):

            XmlSigningService.sign(
                electronic_document,
                FailingSigner(),
            )

        electronic_document.refresh_from_db()

        self.assertEqual(
            electronic_document.status,
            SriDocumentStatus.ERROR,
        )

        self.assertEqual(
            electronic_document.error_message,
            "Error simulado de certificado.",
        )
