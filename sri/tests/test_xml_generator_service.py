from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from core.constants.document_status import DocumentStatus
from core.constants.sri import (
    SriEmissionType,
    SriEnvironment,
)

from core.models import (
    Branch,
    Company,
)

from catalog.models import (
    Product,
    Tax,
)

from inventory.models import Warehouse

from people.models import (
    Customer,
    Person,
)

from sales.models import (
    Sale,
    SaleDetail,
    SaleDetailTax,
)

from sri.models import ElectronicDocument
from sri.services.xml_generator_service import (
    XmlGeneratorService,
)


class XmlGeneratorServiceTest(TestCase):

    def setUp(self):

        company_person = Person.objects.create(
            identification="1790000001001",
            person_type="LEGAL",
            full_name="Empresa Test",
        )

        self.company = Company.objects.create(
            person=company_person,
            commercial_name="Empresa Test",
        )


        self.branch = Branch.objects.create(
            company=self.company,
            code="001",
            name="Matriz",
        )


        self.warehouse = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="BOD001",
            name="Principal",
            is_main=True,
        )


        customer_person = Person.objects.create(
            identification="0999999999001",
            person_type="NATURAL",
            full_name="Cliente Test",
        )


        customer = Customer.objects.create(
            person=customer_person,
        )


        self.sale = Sale.objects.create(
            company=self.company,
            branch=self.branch,
            customer=customer,
            warehouse=self.warehouse,
            issue_date=date.today(),
            status=DocumentStatus.CONFIRMED,
            number="SAL-001-000025",
            subtotal=100,
            tax=15,
            total=115,
        )


        self.product = Product.objects.create(
            company=self.company,
            code="PROD001",
            name="Producto Test",
            sale_price=50,
        )


        self.detail = SaleDetail.objects.create(
            sale=self.sale,
            product=self.product,
            line=1,
            quantity=2,
            unit_price=50,
            discount=0,
            subtotal=100,
            tax_amount=15,
            total=115,
        )


        self.tax_model = Tax.objects.create(
            company=self.company,
            code="2",
            name="IVA",
        )


        self.tax = SaleDetailTax.objects.create(
            detail=self.detail,
            tax=self.tax_model,
            tax_code="2",
            tax_name="IVA",
            tax_type="IVA",
            rate=15,
            base=100,
            amount=15,
        )


        content_type = ContentType.objects.get_for_model(
            Sale
        )


        self.electronic_document = ElectronicDocument.objects.create(
            company=self.company,
            branch=self.branch,
            content_type=content_type,
            object_id=self.sale.id,
            document_type="01",
            environment=SriEnvironment.TEST,
            emission_type=SriEmissionType.NORMAL,
            establishment="001",
            emission_point="001",
            sequential="000000025",
            numeric_code="12345678",
            access_key=(
                "1234567890123456789012345678901234567890123456789"
            ),
        )


    def test_generate_invoice_xml_contains_header(self):

        xml = XmlGeneratorService.generate_invoice(
            self.electronic_document
        )

        self.assertIn(
            "1790000001001",
            xml,
        )

        self.assertIn(
            "Cliente Test",
            xml,
        )

        self.assertIn(
            "000000025",
            xml,
        )


    def test_generate_invoice_xml_contains_details(self):

        xml = XmlGeneratorService.generate_invoice(
            self.electronic_document
        )

        self.assertIn(
            "PROD001",
            xml,
        )

        self.assertIn(
            "Producto Test",
            xml,
        )

        self.assertIn(
            "2",
            xml,
        )

        self.assertIn(
            "50",
            xml,
        )


    def test_generate_invoice_xml_contains_taxes(self):

        xml = XmlGeneratorService.generate_invoice(
            self.electronic_document
        )

        self.assertIn(
            "impuestos",
            xml,
        )

        self.assertIn(
            "IVA",
            xml,
        )

        self.assertIn(
            "15",
            xml,
        )

        self.assertIn(
            "100",
            xml,
        )
    def test_generate_invoice_xml_contains_total_taxes(self):

        xml = XmlGeneratorService.generate_invoice(
            self.electronic_document
        )

        self.assertIn(
            "totalConImpuestos",
            xml,
        )

        self.assertIn(
            "15.00",
            xml,
        )

    def test_generate_invoice_xml_contains_comprobante_id(self):

        xml = XmlGeneratorService.generate_invoice(
            self.electronic_document
        )

        from xml.etree.ElementTree import fromstring

        root = fromstring(xml)

        self.assertEqual(
            root.tag,
            "factura",
        )

        self.assertEqual(
            root.get("id"),
            "comprobante",
        )
