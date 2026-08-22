from decimal import Decimal


class DocumentTotalsService:
    """
    Calcula los totales de un documento.
    """

    @staticmethod
    def calculate(document):

        subtotal = Decimal("0")
        tax = Decimal("0")
        total = Decimal("0")

        for detail in document.details.all():

            detail.subtotal = (
                detail.quantity * detail.unit_price
            ) - detail.discount

            detail.total = (
                detail.subtotal +
                detail.tax_amount
            )

            detail.save()

            subtotal += detail.subtotal
            tax += detail.tax_amount
            total += detail.total

        document.subtotal = subtotal
        document.tax = tax
        document.total = total
        

        document.save(
            update_fields=[
                "subtotal",
                "tax",
                "total",
                "updated_at",
            ]
        )

        document.refresh_from_db()

        return document