from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from core.services.commercial import (
    CommercialLineCalculator,
    CommercialTotalsCalculator,
)


class CommercialLineCalculatorTest(SimpleTestCase):

    def test_calculates_subtotal_without_discount(self):
        self.assertEqual(
            CommercialLineCalculator.calculate_subtotal(
                Decimal("3"), Decimal("10"), Decimal("0"),
            ),
            Decimal("30"),
        )

    def test_calculates_subtotal_with_discount(self):
        self.assertEqual(
            CommercialLineCalculator.calculate_subtotal(
                Decimal("3"), Decimal("10"), Decimal("4.50"),
            ),
            Decimal("25.50"),
        )

    def test_preserves_decimal_precision_without_quantize(self):
        result = CommercialLineCalculator.calculate_subtotal(
            Decimal("1.234567"), Decimal("2.345678"), Decimal("0"),
        )

        self.assertEqual(result, Decimal("2.895896651426"))

    def test_calculates_total_with_tax(self):
        self.assertEqual(
            CommercialLineCalculator.calculate_total(
                Decimal("25.50"), Decimal("4.59"),
            ),
            Decimal("30.09"),
        )

    def test_calculates_total_with_zero_tax(self):
        self.assertEqual(
            CommercialLineCalculator.calculate_total(
                Decimal("25.50"), Decimal("0"),
            ),
            Decimal("25.50"),
        )


class CommercialTotalsCalculatorTest(SimpleTestCase):

    def line(self, subtotal, tax_amount, total):
        return SimpleNamespace(
            subtotal=Decimal(subtotal),
            tax_amount=Decimal(tax_amount),
            total=Decimal(total),
        )

    def test_aggregates_line_values(self):
        result = CommercialTotalsCalculator.calculate([
            self.line("10", "1.50", "11.50"),
            self.line("20", "3", "23"),
        ])

        self.assertEqual(result.subtotal, Decimal("30"))
        self.assertEqual(result.tax, Decimal("4.50"))
        self.assertEqual(result.total, Decimal("34.50"))

    def test_aggregates_subtotal_tax_and_total_directly(self):
        result = CommercialTotalsCalculator.calculate([
            self.line("10", "1.50", "99"),
            self.line("20", "3", "-2"),
        ])

        self.assertEqual(result.subtotal, Decimal("30"))
        self.assertEqual(result.tax, Decimal("4.50"))
        self.assertEqual(result.total, Decimal("97"))

    def test_empty_collection_returns_decimal_zeros(self):
        result = CommercialTotalsCalculator.calculate([])

        self.assertEqual(result.subtotal, Decimal("0"))
        self.assertEqual(result.tax, Decimal("0"))
        self.assertEqual(result.total, Decimal("0"))

    def test_does_not_modify_lines(self):
        lines = [self.line("10", "1.50", "11.50")]
        before = lines[0].__dict__.copy()

        CommercialTotalsCalculator.calculate(lines)

        self.assertEqual(lines[0].__dict__, before)

    def test_returns_immutable_totals(self):
        result = CommercialTotalsCalculator.calculate([])

        with self.assertRaises(AttributeError):
            result.total = Decimal("1")
