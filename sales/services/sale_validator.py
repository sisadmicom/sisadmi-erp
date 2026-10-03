from sales.constants.payment_method import PaymentMethod

from core.validators.document_detail_validator import DocumentDetailValidator
from core.validators.commercial_line_validator import CommercialLineValidator


class SaleValidator:

    @staticmethod
    def validate(dto):

        payment_method = getattr(dto, "payment_method", None)
        if payment_method is not None and payment_method not in PaymentMethod.values:
            raise ValueError("El método de pago no es válido.")

        DocumentDetailValidator.validate_required(bool(dto.details))

        for detail in dto.details:

            CommercialLineValidator.validate(detail)

    @staticmethod
    def validate_confirmation(sale):

        DocumentDetailValidator.validate_required(sale.details.exists())

        for detail in sale.details.all():

            CommercialLineValidator.validate(detail)
