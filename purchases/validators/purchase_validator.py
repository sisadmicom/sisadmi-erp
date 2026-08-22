from core.exceptions import (
    EmptyDocument,
    InvalidPrice,
    InvalidQuantity,
    ValidationException,
)


class PurchaseValidator:

    @staticmethod
    def validate_create(dto):

        if dto.company_id <= 0:
            raise ValidationException("Empresa inválida.")

        if dto.branch_id <= 0:
            raise ValidationException("Sucursal inválida.")

        if dto.supplier_id <= 0:
            raise ValidationException("Proveedor inválido.")

        if not dto.details:
            raise EmptyDocument()

        for detail in dto.details:

            if detail.product_id <= 0:
                raise ValidationException("Producto inválido.")

            if detail.quantity <= 0:
                raise InvalidQuantity()

            if detail.unit_price < 0:
                raise InvalidPrice()

            if detail.discount < 0:
                raise ValidationException(
                    "El descuento no puede ser negativo."
                )

    @staticmethod
    def validate_confirmation(purchase):

        if purchase.is_confirmed():
            raise ValueError(
                "La compra ya fue confirmada."
            )

        if purchase.is_cancelled():
            raise ValueError(
                "La compra fue anulada."
            )

        if purchase.supplier is None:
            raise ValueError(
                "Debe seleccionar un proveedor."
            )

        details = purchase.details.all()

        if not details.exists():
            raise ValueError(
                "La compra no tiene productos."
            )

        for detail in details:

            if detail.quantity <= 0:
                raise ValueError(
                    f"{detail.product.name}: cantidad inválida."
                )

            if detail.unit_price < 0:
                raise ValueError(
                    f"{detail.product.name}: precio inválido."
                )

    @staticmethod
    def validate_cancellation(purchase):

        if purchase.is_cancelled():
            raise ValueError(
                "La compra ya fue anulada."
            )

        if not purchase.is_confirmed():
            raise ValueError(
                "Solo se pueden anular compras confirmadas."
            )

        details = purchase.details.all()

        if not details.exists():
            raise ValueError(
                "La compra no tiene productos."
            )

        for detail in details:

            if detail.quantity <= 0:
                raise ValueError(
                    f"{detail.product.name}: cantidad inválida."
                )