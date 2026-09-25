from django.db import transaction
from core.services.document_service import DocumentService
from inventory.models import InventoryAdjustment, InventoryAdjustmentMovement
from inventory.constants.movement_type import MovementType
from inventory.validators.inventory_adjustment_validator import InventoryAdjustmentValidator
from inventory.services.stock import IncreaseStock, DecreaseStock

class InventoryAdjustmentConfirmationService:
    @staticmethod
    @transaction.atomic
    def confirm(adjustment_id, user=None):
        adjustment = InventoryAdjustment.objects.select_for_update().get(pk=adjustment_id)
        DocumentService.ensure_can_confirm(adjustment)
        direction = adjustment.document_type.inventory_behavior
        details = list(adjustment.details.select_related("product").order_by("product_id"))
        InventoryAdjustmentValidator.validate_document(adjustment, details, direction)
        adjustment = DocumentService.confirm(adjustment, user=user)
        service = IncreaseStock() if direction == "IN" else DecreaseStock()
        movement_type = MovementType.ADJUSTMENT_IN if direction == "IN" else MovementType.ADJUSTMENT_OUT
        for detail in details:
            movement = service.execute(
                company=adjustment.company, branch=adjustment.branch,
                warehouse=adjustment.warehouse, product=detail.product,
                quantity=detail.quantity, movement_type=movement_type,
                document=adjustment, user=user, notes=f"Ajuste {adjustment.number}",
                return_movement=True,
            )
            InventoryAdjustmentMovement.objects.create(
                inventory_adjustment=adjustment, stock_movement=movement,
            )
        return adjustment
