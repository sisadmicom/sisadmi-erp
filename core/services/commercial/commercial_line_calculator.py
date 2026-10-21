from decimal import Decimal, ROUND_HALF_UP


class CommercialLineCalculator:

    @staticmethod
    def monetary_amount(value: Decimal) -> Decimal:
        """Round commercial money at persistence boundaries, never unit values."""
        return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

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
