from django.db import IntegrityError, transaction
from django.test import TestCase

from core.constants.document_type_codes import DocumentTypeCodes
from core.models.document_type import DocumentType

from core.models import Company, Branch, Sequence
from core.services.sequence_service import SequenceService

from people.models import Person
from core.exceptions import ValidationException
from core.exceptions.sequence_exceptions import (
    SequenceInactive,
    SequenceNotFound,
)

class SequenceServiceTest(TestCase):

    def setUp(self):

        # ---------------------------------------------------------
        # EMPRESA
        # ---------------------------------------------------------

        company_person = Person.objects.create(
            identification="1790000001001",
            person_type="LEGAL",
            full_name="Empresa Test",
        )

        self.company = Company.objects.create(
            person=company_person,
            commercial_name="Empresa Test",
        )

        # ---------------------------------------------------------
        # SUCURSAL
        # ---------------------------------------------------------

        self.branch = Branch.objects.create(
            company=self.company,
            code="001",
            name="Matriz",
        )

        # ---------------------------------------------------------
        # SECUENCIA
        # ---------------------------------------------------------

        self.document_type = DocumentType.objects.get(code=DocumentTypeCodes.SALES_INVOICE)
        self.transfer_type = DocumentType.objects.get(code=DocumentTypeCodes.INVENTORY_TRANSFER)
        self.purchase_type = DocumentType.objects.get(code=DocumentTypeCodes.PURCHASE_INVOICE)

        self.sequence = Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
            name="Ventas",
            prefix="VEN-",
            series="001",
            next_number=1,
            padding=6,
            is_active=True,
        )

    # =========================================================
    # TEST 1
    # =========================================================

    def test_generates_first_number(self):

        number = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
        )

        self.assertEqual(
            number,
            "VEN-001-000001",
        )

    # =========================================================
    # TEST 2
    # =========================================================

    def test_increments_sequence(self):

        SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
        )

        self.sequence.refresh_from_db()

        self.assertEqual(
            self.sequence.next_number,
            2,
        )

    # =========================================================
    # TEST 3
    # =========================================================

    def test_generates_sequential_numbers(self):

        number_1 = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
        )

        number_2 = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
        )

        number_3 = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
        )

        self.assertEqual(
            number_1,
            "VEN-001-000001",
        )

        self.assertEqual(
            number_2,
            "VEN-001-000002",
        )

        self.assertEqual(
            number_3,
            "VEN-001-000003",
        )

    # =========================================================
    # TEST 4
    # =========================================================

    def test_respects_padding(self):

        self.sequence.next_number = 25
        self.sequence.padding = 8
        self.sequence.save()

        number = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
        )

        self.assertEqual(
            number,
            "VEN-001-00000025",
        )

    # =========================================================
    # TEST 5
    # =========================================================

    def test_respects_prefix(self):

        self.sequence.prefix = "FACT-"
        self.sequence.save()

        number = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
        )

        self.assertEqual(
            number,
            "FACT-001-000001",
        )

    # =========================================================
    # TEST 6
    # =========================================================

    def test_respects_series(self):

        self.sequence.series = "002"
        self.sequence.save()

        number = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
        )

        self.assertEqual(
            number,
            "VEN-002-000001",
        )

    # =========================================================
    # TEST 7
    # =========================================================

    def test_different_document_type_is_independent(self):

        Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            document_type=self.transfer_type,
            name="Transferencias",
            prefix="TRF-",
            series="001",
            next_number=1,
            padding=6,
            is_active=True,
        )

        sale_number = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
        )

        transfer_number = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.transfer_type,
        )

        self.assertEqual(
            sale_number,
            "VEN-001-000001",
        )

        self.assertEqual(
            transfer_number,
            "TRF-001-000001",
        )

    # =========================================================
    # TEST 8
    # =========================================================

    def test_inactive_sequence_fails(self):

        self.sequence.is_active = False
        self.sequence.save()

        with self.assertRaises(SequenceInactive):

            SequenceService.next_number(
                company=self.company,
                branch=self.branch,
                document_type=self.document_type,
            )

    # =========================================================
    # TEST 9
    # =========================================================

    def test_nonexistent_sequence_fails(self):

        with self.assertRaises(SequenceNotFound):

            SequenceService.next_number(
                company=self.company,
                branch=self.branch,
                document_type=self.purchase_type,
            )

    # =========================================================
    # TEST 10
    # =========================================================

    def test_sequence_belongs_to_branch(self):

        number = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            document_type=self.document_type,
        )

        self.assertEqual(
            number,
            "VEN-001-000001",
        )

        self.sequence.refresh_from_db()

        self.assertEqual(
            self.sequence.next_number,
            2,
        )

    def test_transaction_rollback_does_not_consume_number(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                SequenceService.next_number(self.company, self.branch, self.document_type)
                raise RuntimeError("Rollback")
        self.sequence.refresh_from_db()
        self.assertEqual(self.sequence.next_number, 1)

    def test_missing_type_does_not_consume_sequence(self):
        with self.assertRaises(SequenceNotFound):
            SequenceService.next_number(self.company, self.branch, None)
        self.sequence.refresh_from_db()
        self.assertEqual(self.sequence.next_number, 1)

    def test_scope_is_company_branch_and_document_type(self):
        person = Person.objects.create(
            identification="1790000002001", person_type="LEGAL", full_name="Otra empresa",
        )
        other_company = Company.objects.create(person=person)
        other_branch = Branch.objects.create(company=other_company, code="001", name="Otra")
        second_branch = Branch.objects.create(company=self.company, code="002", name="Sucursal")
        for company, branch in ((other_company, other_branch), (self.company, second_branch)):
            Sequence.objects.create(
                company=company, branch=branch, document_type=self.document_type,
                name="Otra", prefix="OTHER-", next_number=40,
            )
            self.assertEqual(
                SequenceService.next_number(company, branch, self.document_type),
                "OTHER-001-000040",
            )
        with self.assertRaises(ValidationException):
            SequenceService.next_number(other_company, self.branch, self.document_type)
        self.sequence.refresh_from_db()
        self.assertEqual(self.sequence.next_number, 1)

    def test_duplicate_document_type_in_same_scope_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sequence.objects.create(
                company=self.company, branch=self.branch, document_type=self.document_type,
                name="Duplicada", prefix="DUP-",
            )

    def test_document_type_cannot_be_null(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sequence.objects.filter(pk=self.sequence.pk).update(document_type=None)

    def test_string_uses_document_type_and_numbering_configuration(self):
        self.assertEqual(str(self.sequence), "SALES_INVOICE - VEN-001")

    def test_foreign_branch_cannot_consume_even_an_inconsistent_sequence(self):
        person = Person.objects.create(
            identification="1790000002001", person_type="LEGAL", full_name="Otra empresa",
        )
        other_company = Company.objects.create(person=person)
        inconsistent = Sequence.objects.create(
            company=other_company, branch=self.branch, document_type=self.document_type,
            name="Contexto histórico inválido", prefix="OLD-",
            next_number=25,
        )
        with self.assertRaisesMessage(
            ValidationException, "La sucursal no pertenece a la empresa indicada.",
        ):
            SequenceService.next_number(other_company, self.branch, self.document_type)

        inconsistent.refresh_from_db()
        self.sequence.refresh_from_db()
        self.assertEqual(inconsistent.next_number, 25)
        self.assertEqual(self.sequence.next_number, 1)

        self.assertEqual(
            SequenceService.next_number(self.company, self.branch, self.document_type),
            "VEN-001-000001",
        )
        self.sequence.refresh_from_db()
        inconsistent.refresh_from_db()
        self.assertEqual(self.sequence.next_number, 2)
        self.assertEqual(inconsistent.next_number, 25)
