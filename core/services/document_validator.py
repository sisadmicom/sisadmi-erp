from decimal import Decimal


class DocumentValidator:
    """
    Validador genérico de documentos ERP.
    """

    @staticmethod
    def validate(document):

        if not document.is_draft():
            raise ValueError(
                "Solo se pueden confirmar documentos en borrador."
            )

        details = list(document.details.all())

        if not details:
            raise ValueError(
                "El documento no tiene detalles."
            )

        for detail in details:

            if detail.quantity <= 0:
                raise ValueError(
                    "La cantidad debe ser mayor que cero."
                )

            if detail.unit_price < Decimal("0"):
                raise ValueError(
                    "El precio no puede ser negativo."
                )

            if detail.total < Decimal("0"):
                raise ValueError(
                    "El total no puede ser negativo."
                )

        return True