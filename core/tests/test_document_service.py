from contextlib import ExitStack
from unittest.mock import Mock, PropertyMock, patch
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models.base_document import BaseDocument
from core.exceptions import ValidationException

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

    def test_confirm_persists_audit_without_details(self):
        document = self.create_document()
        document.details.all().delete()
        user = get_user_model().objects.create_user(username="document-auditor")
        before = timezone.now()
        result = DocumentService.confirm(document, user=user)
        document.refresh_from_db()
        self.assertIs(result, document)
        self.assertEqual(document.number, "TST-001-000001")
        self.assertEqual(document.status, DocumentStatus.CONFIRMED)
        self.assertEqual(document.confirmed_by, user)
        self.assertGreaterEqual(document.confirmed_at, before)
        self.assertLessEqual(document.confirmed_at, timezone.now())

    def test_confirm_preserves_totals_and_detail_values(self):
        document = self.create_document()
        Sale.objects.filter(pk=document.pk).update(
            subtotal=Decimal("80"), tax=Decimal("9"), total=Decimal("89"),
        )
        document.refresh_from_db()
        detail_values = list(document.details.values())
        DocumentService.confirm(document)
        document.refresh_from_db()
        self.assertEqual((document.subtotal, document.tax, document.total), (Decimal("80"), Decimal("9"), Decimal("89")))
        self.assertEqual(list(document.details.values()), detail_values)

    def test_lifecycle_never_inspects_commercial_structure(self):
        # Only persistence is mocked; numbering uses the real Sequence service.
        document = Mock(spec_set=BaseDocument)
        document.company = self.company
        document.branch = self.branch
        document.document_type = DocumentType.objects.get(code=DocumentTypeCodes.SALES_INVOICE)
        document.status = DocumentStatus.DRAFT
        document.is_draft.side_effect = lambda: document.status == DocumentStatus.DRAFT
        document.is_confirmed.side_effect = lambda: document.status == DocumentStatus.CONFIRMED
        document.is_cancelled.side_effect = lambda: document.status == DocumentStatus.CANCELLED
        with ExitStack() as stack:
            for attribute in ("details", "quantity", "unit_price", "subtotal", "tax", "total"):
                stack.enter_context(patch.object(
                    type(document), attribute, create=True, new_callable=PropertyMock,
                    side_effect=AssertionError(f"Acceso comercial prohibido: {attribute}"),
                ))
            self.assertIs(DocumentService.confirm(document), document)
            self.assertEqual(document.status, DocumentStatus.CONFIRMED)
            self.assertEqual(document.number, "TST-001-000001")
            self.assertIsNotNone(document.confirmed_at)
            self.assertIs(DocumentService.cancel(document), document)
            self.assertEqual(document.status, DocumentStatus.CANCELLED)
            self.assertIsNotNone(document.cancelled_at)
        self.assertEqual(document.save.call_count, 2)
        sequence = Sequence.objects.get(company=self.company, branch=self.branch, document_type=document.document_type)
        self.assertEqual(sequence.next_number, 2)

    def test_confirm_rejects_non_draft_without_consuming_sequence(self):
        for status in (DocumentStatus.CONFIRMED, DocumentStatus.CANCELLED):
            with self.subTest(status=status):
                document = self.create_document()
                document.status = status
                document.save(update_fields=["status"])
                with self.assertRaisesMessage(ValueError, "Solo se pueden confirmar documentos en borrador."):
                    DocumentService.confirm(document)
                document.refresh_from_db()
                self.assertEqual(document.status, status)
                self.assertEqual(document.number, "")
                self.assertIsNone(document.confirmed_at)
                self.assertIsNone(document.confirmed_by)
        self.assertEqual(Sequence.objects.get(company=self.company, branch=self.branch).next_number, 1)

    def test_confirm_delegates_company_branch_validation(self):
        document = self.create_document()
        other_person = Person.objects.create(
            identification="1790000002001", person_type="LEGAL", full_name="Otra empresa",
        )
        document.company = Company.objects.create(person=other_person)
        with self.assertRaises(ValidationException):
            DocumentService.confirm(document)
        document.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.DRAFT)
        self.assertEqual(document.number, "")
        self.assertIsNone(document.confirmed_at)
        self.assertEqual(Sequence.objects.get(company=self.company, branch=self.branch).next_number, 1)

    def test_cancel_persists_audit_without_details_or_consuming_number(self):
        document = self.create_document()
        document.details.all().delete()
        document.status = DocumentStatus.CONFIRMED
        document.number = "EXISTING-001"
        document.save(update_fields=["status", "number"])
        user = get_user_model().objects.create_user(username="document-canceller")
        before = timezone.now()
        self.assertIs(DocumentService.cancel(document, user=user), document)
        document.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.CANCELLED)
        self.assertEqual(document.number, "EXISTING-001")
        self.assertEqual(document.cancelled_by, user)
        self.assertGreaterEqual(document.cancelled_at, before)
        self.assertLessEqual(document.cancelled_at, timezone.now())
        self.assertEqual(Sequence.objects.get(company=self.company, branch=self.branch).next_number, 1)

    def test_cancel_rejects_draft_and_cancelled(self):
        for status, message in (
            (DocumentStatus.DRAFT, "Solo se pueden anular documentos confirmados."),
            (DocumentStatus.CANCELLED, "El documento ya fue anulado."),
        ):
            with self.subTest(status=status):
                document = self.create_document()
                document.status = status
                document.save(update_fields=["status"])
                with self.assertRaisesMessage(ValueError, message):
                    DocumentService.cancel(document)
                document.refresh_from_db()
                self.assertEqual(document.status, status)
                self.assertIsNone(document.cancelled_at)
                self.assertIsNone(document.cancelled_by)
