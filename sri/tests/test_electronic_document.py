from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from core.constants.document_status import DocumentStatus
from core.constants.sri import SriEnvironment, SriEmissionType
from core.models import (
    Branch,
    Company,
    PointOfEmission,
)
from inventory.models import Warehouse
from people.models import Customer, Person
from sales.models import Sale

from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument


class ElectronicDocumentTest(TestCase):

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

        self.sale = Sale.objects.create(
            company=self.company,
            branch=self.branch,
            customer=self.customer,
            warehouse=self.warehouse,
            issue_date=date.today(),
            status=DocumentStatus.CONFIRMED,
            subtotal=100,
            tax=15,
            total=115,
        )

    def test_create_electronic_document(self):

        sale_content_type = ContentType.objects.get_for_model(
            Sale
        )

        document = ElectronicDocument.objects.create(
            company=self.company,
            branch=self.branch,
            content_type=sale_content_type,
            object_id=self.sale.id,
            document_type="01",
            environment=SriEnvironment.TEST,
            emission_type=SriEmissionType.NORMAL,
            establishment="001",
            emission_point="001",
            sequential="000000001",
        )

        self.assertEqual(
            document.company,
            self.company,
        )

        self.assertEqual(
            document.branch,
            self.branch,
        )

        self.assertEqual(
            document.document,
            self.sale,
        )

        self.assertEqual(
            document.content_type,
            sale_content_type,
        )

        self.assertEqual(
            document.object_id,
            self.sale.id,
        )

        self.assertEqual(
            document.document_type,
            "01",
        )

        self.assertEqual(
            document.environment,
            SriEnvironment.TEST,
        )

        self.assertEqual(
            document.emission_type,
            SriEmissionType.NORMAL,
        )

        self.assertEqual(
            document.establishment,
            "001",
        )

        self.assertEqual(
            document.emission_point,
            "001",
        )

        self.assertEqual(
            document.sequential,
            "000000001",
        )

        self.assertEqual(
            document.status,
            SriDocumentStatus.DRAFT,
        )