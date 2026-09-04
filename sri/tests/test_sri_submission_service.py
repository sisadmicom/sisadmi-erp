from django.test import TestCase

from sri.constants.document_status import SriDocumentStatus
from sri.services.sri_submission_service import (
    SriSubmissionService,
)

from sri.tests.helpers import (
    create_test_electronic_document,
)


class FakeSriClient:

    def __init__(self):

        self.called = False
        self.received_xml = None
        self.received_environment = None

    def send(
        self,
        xml,
        environment,
    ):

        self.called = True
        self.received_xml = xml
        self.received_environment = environment

        return {
            "success": True,
            "message": "Documento recibido.",
        }


class FailingSriClient:

    def send(
        self,
        xml,
        environment,
    ):

        raise RuntimeError(
            "Error de comunicación con SRI."
        )


class SriSubmissionServiceTest(TestCase):

    def setUp(self):

        self.electronic_document = (
            create_test_electronic_document()
        )

        self.electronic_document.xml = """
        <factura>
            <infoTributaria/>
            <infoFactura/>
            <detalles>
                <detalle/>
            </detalles>
        </factura>
        """

        self.electronic_document.status = (
            SriDocumentStatus.SIGNED
        )

        self.electronic_document.save(
            update_fields=[
                "xml",
                "status",
            ]
        )

    def test_submit_signed_document(self):

        client = FakeSriClient()

        result = SriSubmissionService.submit(
            electronic_document=self.electronic_document,
            client=client,
        )

        self.assertTrue(
            client.called
        )

        self.assertEqual(
            client.received_xml,
            self.electronic_document.xml,
        )

        self.assertEqual(
            client.received_environment,
            self.electronic_document.environment,
        )

        self.assertEqual(
            result["success"],
            True,
        )

        self.electronic_document.refresh_from_db()

        self.assertEqual(
            self.electronic_document.status,
            SriDocumentStatus.SENT,
        )

    def test_rejects_unsigned_document(self):

        self.electronic_document.status = (
            SriDocumentStatus.GENERATED
        )

        self.electronic_document.save(
            update_fields=["status"]
        )

        client = FakeSriClient()

        with self.assertRaisesMessage(
            ValueError,
            "Solo se pueden enviar al SRI "
            "documentos firmados.",
        ):

            SriSubmissionService.submit(
                electronic_document=self.electronic_document,
                client=client,
            )

        self.assertFalse(
            client.called
        )

    def test_rejects_document_without_xml(self):

        self.electronic_document.xml = ""

        self.electronic_document.save(
            update_fields=["xml"]
        )

        client = FakeSriClient()

        with self.assertRaisesMessage(
            ValueError,
            "El documento electrónico no tiene XML.",
        ):

            SriSubmissionService.submit(
                electronic_document=self.electronic_document,
                client=client,
            )

        self.assertFalse(
            client.called
        )

    def test_changes_status_to_error_when_client_fails(self):

        client = FailingSriClient()

        with self.assertRaisesMessage(
            RuntimeError,
            "Error de comunicación con SRI.",
        ):

            SriSubmissionService.submit(
                electronic_document=self.electronic_document,
                client=client,
            )

        self.electronic_document.refresh_from_db()

        self.assertEqual(
            self.electronic_document.status,
            SriDocumentStatus.ERROR,
        )

        self.assertEqual(
            self.electronic_document.error_message,
            "Error de comunicación con SRI.",
        )
