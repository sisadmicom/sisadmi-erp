from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree as ET

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from catalog.constants.tax_category import TaxCategory
from core.models import SriConfiguration, Sequence
from inventory.models import Stock
from sales.constants.payment_method import PaymentMethod
from sales.models import Sale
from sri.models import ElectronicDocument
from sri.services.xml_generator_service import XmlGeneratorService
from sri.services.xml_validation_service import XmlValidationService
from sri.tests.helpers.invoice_factory import create_test_invoice_environment


class FiscalMappingTests(SimpleTestCase):
    def test_missing_snapshot_type_never_falls_back_to_internal_code(self):
        from sri.services.invoice_fiscal_mapping import vat_codes
        with self.assertRaises(ValueError):
            vat_codes(SimpleNamespace(tax_type="", tax_code="2", tax_name="IVA",
                                      tax_category=TaxCategory.VAT_STANDARD, rate=Decimal("15")))

    def test_tax_codes_use_snapshot_type_category_and_rate_not_internal_code(self):
        from sri.services.invoice_fiscal_mapping import vat_codes
        for category, rate, expected in ((TaxCategory.VAT_STANDARD, "15", "4"),
                (TaxCategory.VAT_STANDARD, "12", "2"), (TaxCategory.VAT_ZERO_RATED, "0", "0"),
                (TaxCategory.VAT_EXEMPT, "0", "7"), (TaxCategory.VAT_NOT_SUBJECT, "0", "6")):
            with self.subTest(category=category):
                snapshot = SimpleNamespace(tax_type="IVA", tax_code="INTERNAL-42", tax_category=category, rate=Decimal(rate))
                self.assertEqual(vat_codes(snapshot), ("2", expected))

    def test_unclassified_zero_and_unknown_rates_never_guess_fiscal_codes(self):
        from sri.services.invoice_fiscal_mapping import vat_codes
        for category, rate in ((None, "0"), (TaxCategory.VAT_STANDARD, "9"), (TaxCategory.VAT_EXEMPT, "15")):
            with self.subTest(category=category, rate=rate), self.assertRaises(ValueError):
                vat_codes(SimpleNamespace(tax_type="IVA", tax_code="2", tax_category=category, rate=Decimal(rate)))


class InvoiceXMLFromHTTPTests(TestCase):
    def setUp(self):
        self.env = create_test_invoice_environment()
        company = self.env["company"]
        issuer = company.person
        issuer.identification_type = "RUC"
        issuer.address = "Dirección matriz de prueba"
        issuer.save()
        branch = self.env["branch"]
        branch.address = "Dirección establecimiento de prueba"
        branch.save()
        buyer = self.env["customer"].person
        buyer.identification_type = "RUC"
        buyer.save()
        self.env["customer"].company = company
        self.env["customer"].save()
        tax = self.env["tax"]
        tax.tax_type = "IVA"
        tax.tax_category = TaxCategory.VAT_STANDARD
        tax.code = "INTERNAL-VAT15"
        tax.save()
        SriConfiguration.objects.create(company=company, environment="1", accounting_required=True)
        Sequence.objects.create(company=company, branch=branch, document_type=self.env["sale"].document_type,
                                name="R04 sales", prefix="VEN-", series="001", padding=6)
        Stock.objects.create(company=company, branch=branch, warehouse=self.env["warehouse"], product=self.env["product"], quantity=Decimal("10"))
        user = get_user_model().objects.create_user("r04-invoice")
        user.profile.companies.add(company)
        user.profile.branches.add(branch)
        self.client.force_login(user)
        session = self.client.session
        session.update({"company_id": company.pk, "branch_id": branch.pk})
        session.save()

    def prepare_from_http(self):
        payload = dict(customer_id=self.env["customer"].pk, warehouse_id=self.env["warehouse"].pk,
            issue_date="2026-10-15", notes="R04 electronic invoice", payment_method=PaymentMethod.CREDIT_CARD,
            **{"details-TOTAL_FORMS": "1", "details-INITIAL_FORMS": "0", "details-MIN_NUM_FORMS": "1", "details-MAX_NUM_FORMS": "1000",
               "details-0-product_id": self.env["product"].pk, "details-0-quantity": "2", "details-0-unit_price": "50", "details-0-discount": "0"})
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No SRI submission")):
            response = self.client.post(reverse("sale_create"), payload)
            self.assertEqual(response.status_code, 302)
            sale = Sale.objects.latest("pk")
            response = self.client.post(reverse("sale_confirm", args=[sale.pk]))
            self.assertEqual(response.status_code, 302)
            sale.refresh_from_db()
            self.assertEqual(sale.status, "CONFIRMED")
            response = self.client.post(reverse("sale_prepare_fiscal", args=[sale.pk]), {"point_of_emission": self.env["emission_point"].pk})
            self.assertEqual(response.status_code, 302)
        return sale, ElectronicDocument.objects.get(object_id=sale.pk)

    def test_sale_from_interface_generates_xsd_valid_invoice_with_vat_and_payment(self):
        sale, document = self.prepare_from_http()
        self.assertTrue(XmlValidationService.validate_for_sri(document.xml))
        root = ET.fromstring(document.xml)
        self.assertEqual(root.get("version"), "1.1.0")
        for path, value in {
            "infoTributaria/ambiente": "1", "infoTributaria/codDoc": "01",
            "infoTributaria/estab": "001", "infoTributaria/ptoEmi": "001",
            "infoTributaria/dirMatriz": "Dirección matriz de prueba",
            "infoFactura/fechaEmision": "15/10/2026", "infoFactura/tipoIdentificacionComprador": "04",
            "infoFactura/pagos/pago/formaPago": "19", "infoFactura/pagos/pago/total": "115.00",
            "infoFactura/totalSinImpuestos": "100.00", "infoFactura/importeTotal": "115.00",
            "infoFactura/totalConImpuestos/totalImpuesto/codigo": "2",
            "infoFactura/totalConImpuestos/totalImpuesto/codigoPorcentaje": "4",
            "detalles/detalle/impuestos/impuesto/codigo": "2",
            "detalles/detalle/impuestos/impuesto/codigoPorcentaje": "4",
        }.items():
            self.assertEqual(root.findtext(path), value, path)
        self.assertEqual(sale.payment_method, PaymentMethod.CREDIT_CARD)
        self.assertEqual(sale.total, Decimal("115.00"))
        self.assertEqual(root.findtext("infoTributaria/claveAcceso"), document.access_key)
        self.assertIsNone(root.find(".//impuesto/nombre"))
        self.assertIsNone(root.find("{http://www.w3.org/2000/09/xmldsig#}Signature"))
        self.assertEqual(document.status, "GENERATED")

    def test_strict_validation_rejects_schema_and_semantic_errors(self):
        _, document = self.prepare_from_http()
        cases = [("version", None), ("infoFactura/pagos", None),
                 ("infoTributaria/claveAcceso", "1" * 49), ("infoFactura/importeTotal", "116.00"),
                 ("detalles/detalle/impuestos/impuesto/codigoPorcentaje", "2")]
        for path, value in cases:
            with self.subTest(path=path):
                root = ET.fromstring(document.xml)
                if path == "version":del root.attrib["version"]
                elif value is None:root.find("infoFactura").remove(root.find(path))
                else:root.find(path).text = value
                with self.assertRaises(ValueError):
                    XmlValidationService.validate_for_sri(ET.tostring(root, encoding="unicode"))

    def test_snapshot_and_stored_xml_are_not_reinterpreted_after_catalog_edits(self):
        sale, document = self.prepare_from_http()
        xml = document.xml
        snapshot = list(sale.details.first().applied_taxes.values())
        self.env["tax"].rate = Decimal("12")
        self.env["tax"].code = "CHANGED"
        self.env["tax"].save()
        self.assertEqual(XmlGeneratorService.generate_invoice(document), xml)
        document.refresh_from_db()
        self.assertEqual(document.xml, xml)
        self.assertEqual(list(sale.details.first().applied_taxes.values()), snapshot)


class OfflineInvoiceValidationTests(SimpleTestCase):
    def valid_xml(self):
        from sri.services.access_key_service import AccessKeyService
        key = AccessKeyService.generate(issue_date=date(2026, 10, 15), document_type="01",
            ruc="1790000001001", environment="1", establishment="001", emission_point="001",
            sequential="000000001", numeric_code="12345678", emission_type="1")
        return f'''<factura id="comprobante" version="1.1.0">
          <infoTributaria><ambiente>1</ambiente><tipoEmision>1</tipoEmision><razonSocial>Issuer test</razonSocial>
          <ruc>1790000001001</ruc><claveAcceso>{key}</claveAcceso><codDoc>01</codDoc><estab>001</estab>
          <ptoEmi>001</ptoEmi><secuencial>000000001</secuencial><dirMatriz>Test address</dirMatriz></infoTributaria>
          <infoFactura><fechaEmision>15/10/2026</fechaEmision><tipoIdentificacionComprador>04</tipoIdentificacionComprador>
          <razonSocialComprador>Buyer test</razonSocialComprador><identificacionComprador>0999999999001</identificacionComprador>
          <totalSinImpuestos>100.00</totalSinImpuestos><totalDescuento>0.00</totalDescuento><totalConImpuestos>
          <totalImpuesto><codigo>2</codigo><codigoPorcentaje>4</codigoPorcentaje><baseImponible>100.00</baseImponible>
          <valor>15.00</valor></totalImpuesto></totalConImpuestos><importeTotal>115.00</importeTotal><moneda>DOLAR</moneda>
          <pagos><pago><formaPago>19</formaPago><total>115.00</total></pago></pagos></infoFactura>
          <detalles><detalle><codigoPrincipal>TEST</codigoPrincipal><descripcion>Test product</descripcion><cantidad>2</cantidad>
          <precioUnitario>50.000000</precioUnitario><descuento>0.00</descuento><precioTotalSinImpuesto>100.00</precioTotalSinImpuesto>
          <impuestos><impuesto><codigo>2</codigo><codigoPorcentaje>4</codigoPorcentaje><tarifa>15.00</tarifa>
          <baseImponible>100.00</baseImponible><valor>15.00</valor></impuesto></impuestos></detalle></detalles></factura>'''

    def test_official_xsd_validation_never_requires_network(self):
        with patch("socket.socket.connect", side_effect=AssertionError("Offline schema only")):
            self.assertTrue(XmlValidationService.validate_for_sri(self.valid_xml()))

    def test_dtd_entities_and_schema_location_cannot_fetch_external_resources(self):
        xml = self.valid_xml()
        with patch("socket.socket.connect", side_effect=AssertionError("No external XML fetch")):
            with self.assertRaises(ValueError):
                XmlValidationService.validate_for_sri('<!DOCTYPE factura [<!ENTITY x SYSTEM "file:///etc/passwd">]>' + xml)
            self.assertTrue(XmlValidationService.validate_for_sri(xml.replace('<factura ', '<factura xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="https://invalid.example/evil.xsd" ')))

    def test_schema_and_consistency_failures_are_rejected(self):
        xml = self.valid_xml()
        changes = [('version="1.1.0"', ''), ('<formaPago>19</formaPago>', '<formaPago>99</formaPago>'),
                   ('<importeTotal>115.00</importeTotal>', '<importeTotal>116.00</importeTotal>'),
                   ('<tarifa>15.00</tarifa>', '<tarifa>12.00</tarifa>'),
                   ('<valor>15.00</valor>', '<valor>14.00</valor>')]
        for before, after in changes:
            with self.subTest(before=before), self.assertRaises(ValueError):
                XmlValidationService.validate_for_sri(xml.replace(before, after))
