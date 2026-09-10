from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class CommercialTotals:
    subtotal: Decimal
    tax: Decimal
    total: Decimal


class CommercialTotalsCalculator:

    @staticmethod
    def calculate(lines: Iterable[object]) -> CommercialTotals:
        subtotal = Decimal("0")
        tax = Decimal("0")
        total = Decimal("0")

        for line in lines:
            subtotal += line.subtotal
            tax += line.tax_amount
            total += line.total

        return CommercialTotals(
            subtotal=subtotal,
            tax=tax,
            total=total,
        )
