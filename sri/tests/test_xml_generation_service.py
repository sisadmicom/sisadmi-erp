from django.test import TestCase

from sri.constants.document_status import SriDocumentStatus
from sri.services.xml_generation_service import (
    XmlGenerationService,
)

from sri.tests.helpers import (
    create_test_electronic_document,
)
from xml.etree.ElementTree import fromstring

class XmlGenerationServiceTest(TestCase):
    """
    Pruebas del servicio de generación
    y almacenamiento de XML.
    """


    def test_generate_xml_saves_document(self):

        electronic_document = (
            create_test_electronic_document()
        )


        result = XmlGenerationService.generate(
            electronic_document
        )

        result.refresh_from_db()

        root = fromstring(
            electronic_document.xml
        )

        self.assertIsNotNone(
            result.xml
        )


        self.assertEqual(
            root.tag,
            "factura",
        )

        self.assertEqual(
            root.get("id"),
            "comprobante",
        )
