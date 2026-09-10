from decimal import Decimal


class CommercialLineCalculator:

    @staticmethod
    def calculate_subtotal(
        quantity: Decimal,
        unit_price: Decimal,
        discount: Decimal,
    ) -> Decimal:
        return quantity * unit_price - discount

    @staticmethod
    def calculate_total(
        subtotal: Decimal,
        tax_amount: Decimal,
    ) -> Decimal:
        return subtotal + tax_amount
