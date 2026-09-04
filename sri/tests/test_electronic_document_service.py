#sri/tests/test_electronic_document_service.py
from datetime import date

from django.test import TestCase

from core.constants.document_status import DocumentStatus
from core.constants.sri import (
    SriEmissionType,
    SriEnvironment,
)
from core.models import Branch, Company
from core.models.point_of_emission import PointOfEmission

from inventory.models import Warehouse
from people.models import Customer, Person
from sales.models import Sale

from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument
from sri.services.electronic_document_service import (
    ElectronicDocumentService,
)


class ElectronicDocumentServiceTest(TestCase):

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
            number="SAL-001-000025",
            subtotal=100,
            tax=15,
            total=115,
        )

        self.emission_point = PointOfEmission.objects.create(

            branch=self.branch,
            code="001",
            name="Caja Principal",
            is_active=True,
        )

    def test_create_electronic_document(self):

        electronic_document = (
            ElectronicDocumentService.create(
                document=self.sale,
                document_type="01",
                emission_point=self.emission_point,
                environment=SriEnvironment.TEST,
                emission_type=SriEmissionType.NORMAL,
            )
        )

        self.assertEqual(
            electronic_document.company,
            self.company,
        )

        self.assertEqual(
            electronic_document.branch,
            self.branch,
        )

        self.assertEqual(
            electronic_document.document,
            self.sale,
        )

        self.assertEqual(
            electronic_document.document_type,
            "01",
        )

        self.assertEqual(
            electronic_document.environment,
            SriEnvironment.TEST,
        )

        self.assertEqual(
            electronic_document.emission_type,
            SriEmissionType.NORMAL,
        )

        self.assertEqual(
            electronic_document.establishment,
            "001",
        )

        self.assertEqual(
            electronic_document.emission_point,
            "001",
        )

        self.assertEqual(
            electronic_document.sequential,
            "000000025",
        )

        self.assertEqual(
            electronic_document.status,
            SriDocumentStatus.DRAFT,
        )

    def test_rejects_draft_document(self):

        self.sale.status = DocumentStatus.DRAFT
        self.sale.save(
            update_fields=["status"]
        )

        with self.assertRaisesMessage(
            ValueError,
            "Solo se puede generar un documento electrónico "
            "a partir de un documento confirmado.",
        ):

            ElectronicDocumentService.create(
                document=self.sale,
                document_type="01",
                emission_point=self.emission_point,
                environment=SriEnvironment.TEST,
                emission_type=SriEmissionType.NORMAL,
            )

    def test_rejects_document_without_number(self):

        self.sale.number = ""
        self.sale.save(
            update_fields=["number"]
        )

        with self.assertRaisesMessage(
            ValueError,
            "El documento debe tener un número antes de "
            "generar el documento electrónico.",
        ):

            ElectronicDocumentService.create(
                document=self.sale,
                document_type="01",
                emission_point=self.emission_point,
                environment=SriEnvironment.TEST,
                emission_type=SriEmissionType.NORMAL,
            )

    def test_rejects_inactive_emission_point(self):

        self.emission_point.is_active = False
        self.emission_point.save(
            update_fields=["is_active"]
        )

        with self.assertRaisesMessage(
            ValueError,
            "El punto de emisión está inactivo.",
        ):

            ElectronicDocumentService.create(
                document=self.sale,
                document_type="01",
                emission_point=self.emission_point,
                environment=SriEnvironment.TEST,
                emission_type=SriEmissionType.NORMAL,
            )
    def test_rejects_duplicate_electronic_document(self):

        ElectronicDocumentService.create(
            document=self.sale,
            document_type="01",
            emission_point=self.emission_point,
            environment=SriEnvironment.TEST,
            emission_type=SriEmissionType.NORMAL,
        )

        with self.assertRaisesMessage(
            ValueError,
            "El documento ya tiene un documento electrónico generado.",
        ):

            ElectronicDocumentService.create(
                document=self.sale,
                document_type="01",
                emission_point=self.emission_point,
                environment=SriEnvironment.TEST,
                emission_type=SriEmissionType.NORMAL,
            )
