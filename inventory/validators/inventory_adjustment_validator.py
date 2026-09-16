from decimal import Decimal
from django.core.exceptions import ValidationError
from core.constants.document_category import DocumentCategory
from core.constants.line_behavior import LineBehavior
from core.constants.inventory_behavior import InventoryBehavior
from core.validators.document_detail_validator import DocumentDetailValidator
from core.validators.quantity_line_validator import QuantityLineValidator
from core.validators.operational_context_validator import OperationalContextValidator

class InventoryAdjustmentValidator:
    @staticmethod
    def validate_quantity(quantity):
        if not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity <= 0:
            raise ValidationError("La cantidad debe ser un Decimal finito mayor que cero.")
        if -quantity.as_tuple().exponent > 6:
            raise ValidationError("La cantidad debe tener como máximo seis decimales.")
        if quantity >= Decimal("1000000000000"):
            raise ValidationError("La cantidad excede el rango permitido.")
        QuantityLineValidator.validate(type("Line", (), {"quantity": quantity})())

    @classmethod
    def validate_type(cls, document_type, direction):
        expected = InventoryBehavior.IN if direction == "IN" else InventoryBehavior.OUT
        if not document_type or not document_type.is_active or document_type.code != f"INVENTORY_ADJUSTMENT_{direction}" or document_type.category != DocumentCategory.INVENTORY or document_type.line_behavior != LineBehavior.QUANTITY or not document_type.requires_detail or not document_type.affects_inventory or document_type.inventory_behavior != expected or document_type.can_issue_electronic:
            raise ValidationError("El tipo documental de ajuste no es compatible.")

    @classmethod
    def validate_create(cls, dto, company, branch, warehouse, products, document_type, direction):
        DocumentDetailValidator.validate_required(bool(dto.details))
        if dto.notes is None or not str(dto.notes).strip():
            raise ValidationError("Las notas son obligatorias.")
        OperationalContextValidator.validate_company_branch(company, branch)
        OperationalContextValidator.validate_warehouse(company, branch, warehouse)
        cls.validate_type(document_type, direction)
        seen = set()
        for item, product in zip(dto.details, products):
            cls.validate_quantity(item.quantity)
            if item.product_id in seen:
                raise ValidationError("No se puede repetir un producto en un ajuste.")
            seen.add(item.product_id)
            OperationalContextValidator.validate_product(company, product)

    @classmethod
    def validate_document(cls, adjustment, details, direction):
        cls.validate_type(adjustment.document_type, direction)
        if not adjustment.notes or not adjustment.notes.strip():
            raise ValidationError("Las notas son obligatorias.")
        OperationalContextValidator.validate_company_branch(adjustment.company, adjustment.branch)
        OperationalContextValidator.validate_warehouse(adjustment.company, adjustment.branch, adjustment.warehouse)
        seen = set()
        DocumentDetailValidator.validate_required(bool(details))
        for item in details:
            cls.validate_quantity(item.quantity)
            if item.product_id in seen:
                raise ValidationError("No se puede repetir un producto en un ajuste.")
            seen.add(item.product_id)
            OperationalContextValidator.validate_product(adjustment.company, item.product)
