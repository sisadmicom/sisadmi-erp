from decimal import Decimal

from catalog.models import Tax


class TaxCalculationService:

    @staticmethod
    def calculate(base: Decimal, taxes):
        """
        Calcula los impuestos aplicables sobre una base imponible.

        Retorna una lista de diccionarios con:
            tax
            base
            rate
            amount
        """

        base = Decimal(base)

        results = []

        for tax in taxes:

            rate = Decimal(tax.rate)

            amount = (
                base * rate / Decimal("100")
            ).quantize(Decimal("0.01"))

            results.append(
                {
                    "tax": tax,
                    "base": base,
                    "rate": rate,
                    "amount": amount,
                }
            )

        return results
