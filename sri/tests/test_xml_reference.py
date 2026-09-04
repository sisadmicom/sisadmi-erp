from django.test import TestCase

from sri.services.xml_generator_service import (
    XmlGeneratorService,
)

from sri.tests.helpers import (
    create_test_electronic_document,
)


class XmlReferenceTest(TestCase):

    def test_print_generated_xml(self):

        document = create_test_electronic_document()

        xml = XmlGeneratorService.generate_invoice(
            document
        )

        print("\n")
        print(xml)
        print("\n")
