from decimal import Decimal

from core.constants.document_status import DocumentStatus


class SaleValidator:

    @staticmethod
    def validate(dto):

        if not dto.details:
            raise ValueError(
                "La venta no tiene detalles."
            )

        for detail in dto.details:

            if detail.quantity <= 0:
                raise ValueError(
                    "Cantidad inválida."
                )

            if detail.unit_price < Decimal("0"):
                raise ValueError(
                    "Precio inválido."
                )

    @staticmethod
    def validate_confirmation(sale):

        if sale.status != DocumentStatus.DRAFT:
            raise ValueError(
                "La venta ya fue confirmada."
            )

        if not sale.details.exists():
            raise ValueError(
                "La venta no tiene detalles."
            )

        for detail in sale.details.all():

            if detail.quantity <= 0:
                raise ValueError(
                    "Cantidad inválida."
                )

            if detail.unit_price < 0:
                raise ValueError(
                    "Precio inválido."
                )

    @staticmethod
    def validate_cancellation(sale):

        if sale.status == DocumentStatus.CANCELLED:
            raise ValueError(
                "La venta ya fue anulada."
            )

        if sale.status != DocumentStatus.CONFIRMED:
            raise ValueError(
                "Solo se pueden cancelar ventas confirmadas."
            )

        if not sale.details.exists():
            raise ValueError(
                "La venta no tiene detalles."
            )

        for detail in sale.details.all():

            if detail.quantity <= 0:
                raise ValueError(
                    "Cantidad inválida."
                )

            if detail.unit_price < 0:
                raise ValueError(
                    "Precio inválido."
                )