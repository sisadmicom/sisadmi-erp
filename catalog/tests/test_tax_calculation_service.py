from decimal import Decimal

from django.test import TestCase

from catalog.models import Tax
from catalog.services import TaxCalculationService

from core.models import Company
from people.models import Person


class TaxCalculationServiceTest(TestCase):

    def setUp(self):

        self.person = Person.objects.create(
            identification="0999999999981",
            person_type="LEGAL",
            full_name="Empresa Calculo Impuestos",
        )

        self.company = Company.objects.create(
            person=self.person,
            commercial_name="Empresa Calculo Impuestos",
        )

        self.iva = Tax.objects.create(
            company=self.company,
            name="IVA 15%",
            code="IVA15",
            tax_type="IVA",
            rate=Decimal("15.0000"),
        )

        self.ice = Tax.objects.create(
            company=self.company,
            name="ICE 10%",
            code="ICE10",
            tax_type="ICE",
            rate=Decimal("10.0000"),
        )

    def test_calculate_single_tax(self):

        results = TaxCalculationService.calculate(
            Decimal("100.00"),
            [self.iva],
        )

        self.assertEqual(
            len(results),
            1,
        )

        result = results[0]

        self.assertEqual(
            result["tax"],
            self.iva,
        )

        self.assertEqual(
            result["base"],
            Decimal("100.00"),
        )

        self.assertEqual(
            result["rate"],
            Decimal("15.0000"),
        )

        self.assertEqual(
            result["amount"],
            Decimal("15.00"),
        )

    def test_calculate_multiple_taxes(self):

        results = TaxCalculationService.calculate(
            Decimal("100.00"),
            [
                self.iva,
                self.ice,
            ],
        )

        self.assertEqual(
            len(results),
            2,
        )

        self.assertEqual(
            results[0]["amount"],
            Decimal("15.00"),
        )

        self.assertEqual(
            results[1]["amount"],
            Decimal("10.00"),
        )

    def test_calculate_zero_base(self):

        results = TaxCalculationService.calculate(
            Decimal("0.00"),
            [self.iva],
        )

        self.assertEqual(
            results[0]["amount"],
            Decimal("0.00"),
        )

    def test_calculate_decimal_precision(self):

        results = TaxCalculationService.calculate(
            Decimal("33.33"),
            [self.iva],
        )

        self.assertEqual(
            results[0]["amount"],
            Decimal("5.00"),
        )

    def test_calculate_without_taxes(self):

        results = TaxCalculationService.calculate(
            Decimal("100.00"),
            [],
        )

        self.assertEqual(
            results,
            [],
        )
