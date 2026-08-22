from django.test import TestCase

from core.models import Company, Branch, Sequence
from core.services.sequence_service import SequenceService

from people.models import Person
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

        self.sequence = Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            code="SAL",
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
            code="SAL",
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
            code="SAL",
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
            code="SAL",
        )

        number_2 = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            code="SAL",
        )

        number_3 = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            code="SAL",
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
            code="SAL",
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
            code="SAL",
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
            code="SAL",
        )

        self.assertEqual(
            number,
            "VEN-002-000001",
        )

    # =========================================================
    # TEST 7
    # =========================================================

    def test_different_sequence_code_is_independent(self):

        Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            code="TRF",
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
            code="SAL",
        )

        transfer_number = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            code="TRF",
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
                code="SAL",
            )

    # =========================================================
    # TEST 9
    # =========================================================

    def test_nonexistent_sequence_fails(self):

        with self.assertRaises(SequenceNotFound):

            SequenceService.next_number(
                company=self.company,
                branch=self.branch,
                code="XXX",
            )

    # =========================================================
    # TEST 10
    # =========================================================

    def test_sequence_belongs_to_branch(self):

        number = SequenceService.next_number(
            company=self.company,
            branch=self.branch,
            code="SAL",
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
