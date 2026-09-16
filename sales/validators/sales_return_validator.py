from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from core.constants.document_status import DocumentStatus
from core.models import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.validators.operational_context_validator import OperationalContextValidator

class SalesReturnValidator:
    @staticmethod
    def validate_type(document_type):
        if not document_type or document_type.code != DocumentTypeCodes.SALES_RETURN:
            raise ValidationError("Tipo documental inválido para devolución.")
        expected={"category":"SALES","line_behavior":"COMMERCIAL","requires_detail":True,
                  "affects_inventory":True,"inventory_behavior":"IN",
                  "can_issue_electronic":False,"is_active":True}
        if any(getattr(document_type,k) != v for k,v in expected.items()):
            raise ValidationError("DocumentType SALES_RETURN incompatible.")

    @staticmethod
    def validate_quantity(value):
        if not isinstance(value, Decimal):
            raise ValidationError("La cantidad debe ser Decimal.")
        if not value.is_finite() or value <= 0 or value.as_tuple().exponent < -6:
            raise ValidationError("Cantidad inválida.")
        if abs(value) > Decimal("999999999999.999999"):
            raise ValidationError("Cantidad fuera de rango.")

    @classmethod
    def validate_creation(cls, sale, details):
        if sale.status != DocumentStatus.CONFIRMED:
            raise ValidationError("La venta debe estar confirmada.")
        if not details:
            raise ValidationError("La devolución requiere detalles.")
        OperationalContextValidator.validate_company_branch(sale.company, sale.branch)
        OperationalContextValidator.validate_warehouse(sale.company, sale.branch, sale.warehouse)
        seen=set()
        for detail, quantity in details:
            if detail.sale_id != sale.pk:
                raise ValidationError("La línea no pertenece a la venta.")
            if detail.pk in seen:
                raise ValidationError("La línea está repetida.")
            seen.add(detail.pk)
            OperationalContextValidator.validate_product(sale.company, detail.product)
            cls.validate_quantity(quantity)

    @classmethod
    def validate_persisted(cls, ret):
        cls.validate_type(ret.document_type)
        cls.validate_creation(ret.sale, [(d.sale_detail, d.quantity) for d in ret.details.select_related("sale_detail__product")])
        for d in ret.details.select_related("sale_detail__product"):
            if d.product_id != d.sale_detail.product_id:
                raise ValidationError("Snapshot de producto inconsistente.")
