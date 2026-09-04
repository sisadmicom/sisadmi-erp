from django.test import SimpleTestCase

from sri.services.test_xml_signer import TestXmlSigner
from sri.services.xml_signer import XmlSigner


class XmlSignerTest(SimpleTestCase):

    def test_test_signer_implements_xml_signer(self):

        signer = TestXmlSigner()

        self.assertIsInstance(
            signer,
            XmlSigner,
        )

    def test_test_signer_returns_signed_xml(self):

        signer = TestXmlSigner()

        xml = "<factura></factura>"

        signed_xml = signer.sign(xml)

        self.assertIn(
            'firma="TEST-SIGNATURE"',
            signed_xml,
        )

        self.assertNotEqual(
            xml,
            signed_xml,
        )
