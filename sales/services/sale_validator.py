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

        DocumentDetailValidator.validate_required(sale.details.exists())

        for detail in sale.details.all():

            CommercialLineValidator.validate(detail)

    @staticmethod
    def validate_cancellation(sale):

        if not sale.details.exists():
            raise ValueError(
                "La venta no tiene detalles."
            )
