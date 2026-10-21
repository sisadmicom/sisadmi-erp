from django.core.exceptions import ValidationError

from core.exceptions import ValidationException
from core.validators.document_detail_validator import DocumentDetailValidator
from core.validators.commercial_line_validator import CommercialLineValidator


class PurchaseValidator:

    @staticmethod
    def validate_supplier_company(supplier, company_id):
        if supplier.company_id is None:
            raise ValidationError("El proveedor debe tener una empresa clasificada para esta compra.")
        if supplier.company_id != company_id:
            raise ValidationError("El proveedor no pertenece a la empresa de la compra.")

    @staticmethod
    def validate_supplier_for_document(supplier, company_id):
        PurchaseValidator.validate_supplier_company(supplier, company_id)
        if not supplier.is_active:
            raise ValidationError("El proveedor no está activo para esta compra.")

    @staticmethod
    def validate_create(dto):

        if dto.company_id <= 0:
            raise ValidationException("Empresa inválida.")

        if dto.branch_id <= 0:
            raise ValidationException("Sucursal inválida.")

        if dto.supplier_id <= 0:
            raise ValidationException("Proveedor inválido.")

        DocumentDetailValidator.validate_required(bool(dto.details))

        for detail in dto.details:

            if detail.product_id <= 0:
                raise ValidationException("Producto inválido.")

            CommercialLineValidator.validate(detail)

            if detail.discount < 0:
                raise ValidationException(
                    "El descuento no puede ser negativo."
                )

    @staticmethod
    def validate_confirmation(purchase):

        if purchase.supplier is None:
            raise ValueError(
                "Debe seleccionar un proveedor."
            )

        details = purchase.details.all()

        DocumentDetailValidator.validate_required(details.exists())

        for detail in details:

            CommercialLineValidator.validate(detail)
