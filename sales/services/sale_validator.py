from core.constants.document_status import DocumentStatus
from core.validators.document_detail_validator import DocumentDetailValidator
from core.validators.commercial_line_validator import CommercialLineValidator


class SaleValidator:

    @staticmethod
    def validate(dto):

        DocumentDetailValidator.validate_required(bool(dto.details))

        for detail in dto.details:

            CommercialLineValidator.validate(detail)

    @staticmethod
    def validate_confirmation(sale):

        if sale.status != DocumentStatus.DRAFT:
            raise ValueError(
                "La venta ya fue confirmada."
            )

        DocumentDetailValidator.validate_required(sale.details.exists())

        for detail in sale.details.all():

            CommercialLineValidator.validate(detail)

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