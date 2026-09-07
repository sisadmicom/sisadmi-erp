from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.constants.document_type_codes import DocumentTypeCodes
from core.models.document_type import DocumentType
from catalog.models import Product
from core.constants.document_status import DocumentStatus
from core.models import Branch, Company, Sequence
from core.services.document_service import DocumentService
from inventory.models import Warehouse
from people.models import Customer, Person
from sales.models import Sale, SaleDetail


class DocumentServiceTest(TestCase):

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

        self.customer = Customer.objects.create(
            person=customer_person,
        )

        self.product = Product.objects.create(
            company=self.company,
            code="P001",
            name="Producto Test",
            sale_price=Decimal("10.00"),
        )

        Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            document_type=DocumentType.objects.get(code=DocumentTypeCodes.SALES_INVOICE),
            code="CUSTOM-TEST",
            name="Pruebas",
            prefix="TST-",
            series="001",
            next_number=1,
            padding=6,
        )

    def create_document(self):

        document = Sale.objects.create(
            document_type=DocumentType.objects.get(code=Sale.DOCUMENT_TYPE_CODE),
            company=self.company,
            branch=self.branch,
            customer=self.customer,
            warehouse=self.warehouse,
            issue_date=date.today(),
            status=DocumentStatus.DRAFT,
            subtotal=Decimal("10.00"),
            tax=Decimal("0.00"),
            total=Decimal("10.00"),
        )

        SaleDetail.objects.create(
            sale=document,
            line=1,
            product=self.product,
            quantity=Decimal("1"),
            unit_price=Decimal("10.00"),
            discount=Decimal("0.00"),
            subtotal=Decimal("10.00"),
            tax_amount=Decimal("0.00"),
            total=Decimal("10.00"),
        )

        return document

    def test_confirm_generates_number(self):

        document = self.create_document()

        DocumentService.confirm(
            document=document,
            user=None,
        )

        document.refresh_from_db()

        self.assertEqual(
            document.number,
            "TST-001-000001",
        )

    def test_confirm_changes_status(self):

        document = self.create_document()

        self.assertEqual(
            document.status,
            DocumentStatus.DRAFT,
        )

        DocumentService.confirm(
            document=document,
            user=None,
        )

        document.refresh_from_db()

        self.assertEqual(
            document.status,
            DocumentStatus.CONFIRMED,
        )

    def test_confirm_increments_sequence(self):

        document = self.create_document()

        DocumentService.confirm(
            document=document,
            user=None,
        )

        sequence = Sequence.objects.get(
            company=self.company,
            branch=self.branch,
            document_type=document.document_type,
        )

        self.assertEqual(
            sequence.next_number,
            2,
        )

    def test_confirm_generates_sequential_numbers(self):

        document1 = self.create_document()

        DocumentService.confirm(
            document=document1,
            user=None,
        )

        document2 = self.create_document()

        DocumentService.confirm(
            document=document2,
            user=None,
        )

        document1.refresh_from_db()
        document2.refresh_from_db()

        self.assertEqual(
            document1.number,
            "TST-001-000001",
        )

        self.assertEqual(
            document2.number,
            "TST-001-000002",
        )