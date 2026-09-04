from django.test import SimpleTestCase

from sri.services.xml_validation_service import (
    XmlValidationService,
)


class XmlValidationServiceTest(SimpleTestCase):

    def test_valid_xml(self):

        xml = """
        <factura>
            <infoTributaria/>
            <infoFactura/>
            <detalles>
                <detalle/>
            </detalles>
        </factura>
        """

        result = XmlValidationService.validate(xml)

        self.assertTrue(result)


    def test_invalid_xml_without_details(self):

        xml = """
        <factura>
            <infoTributaria/>
            <infoFactura/>
        </factura>
        """

        with self.assertRaises(ValueError):
            XmlValidationService.validate(xml)
