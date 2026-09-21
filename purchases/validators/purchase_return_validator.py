from decimal import Decimal

from django.core.exceptions import ValidationError

from core.constants.document_status import DocumentStatus
from core.constants.document_type_codes import DocumentTypeCodes
from core.validators.operational_context_validator import OperationalContextValidator


class PurchaseReturnValidator:
    @staticmethod
    def validate_type(document_type):
        expected = dict(
            code=DocumentTypeCodes.PURCHASE_RETURN, category="PURCHASES",
            line_behavior="COMMERCIAL", requires_detail=True, affects_inventory=True,
            inventory_behavior="OUT", can_issue_electronic=False, is_active=True,
        )
        if any(getattr(document_type, key) != value for key, value in expected.items()):
            raise ValidationError("DocumentType PURCHASE_RETURN incompatible.")

    @staticmethod
    def validate_quantity(quantity):
        if not isinstance(quantity, Decimal):
            raise ValidationError("La cantidad debe ser Decimal.")
        if (not quantity.is_finite() or quantity <= 0
                or quantity.as_tuple().exponent < -6
                or quantity > Decimal("999999999999.999999")):
            raise ValidationError("Cantidad inválida o fuera de rango.")

    @classmethod
    def validate_lines(cls, purchase, pairs):
        if purchase.status != DocumentStatus.CONFIRMED:
            raise ValidationError("La compra debe estar confirmada.")
        OperationalContextValidator.validate_company_branch(purchase.company, purchase.branch)
        if not pairs:
            raise ValidationError("La devolución requiere detalles.")
        seen = set()
        for source, quantity in pairs:
            if source.purchase_id != purchase.pk:
                raise ValidationError("La línea no pertenece a la compra.")
            if source.pk in seen:
                raise ValidationError("Línea de compra repetida.")
            seen.add(source.pk)
            OperationalContextValidator.validate_product(purchase.company, source.product)
            cls.validate_quantity(quantity)

    @classmethod
    def validate_context(cls, document, purchase):
        cls.validate_type(document.document_type)
        if (document.purchase_id, document.company_id, document.branch_id) != (
            purchase.pk, purchase.company_id, purchase.branch_id,
        ):
            raise ValidationError("Contexto de devolución inconsistente con la compra.")
        OperationalContextValidator.validate_company_branch(document.company, document.branch)
        OperationalContextValidator.validate_warehouse(
            document.company, document.branch, document.warehouse,
        )
