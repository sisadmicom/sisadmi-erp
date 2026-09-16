from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from core.services.document_service import DocumentService
from inventory.models import InventoryAdjustment, StockMovement
from inventory.constants.movement_type import MovementType
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from core.exceptions.inventory import InventoryException

class InventoryAdjustmentCancellationService:
    @staticmethod
    @transaction.atomic
    def cancel(adjustment_id, user=None):
        adjustment = InventoryAdjustment.objects.select_for_update().get(pk=adjustment_id)
        DocumentService.ensure_can_cancel(adjustment)
        ct = ContentType.objects.get_for_model(adjustment)
        originals = list(StockMovement.objects.filter(content_type=ct, object_id=adjustment.pk, reverses__isnull=True, movement_type__in=[MovementType.ADJUSTMENT_IN, MovementType.ADJUSTMENT_OUT]).order_by("product_id", "pk"))
        if not originals:
            raise InventoryException("El ajuste no tiene historia de inventario.")
        expected = MovementType.ADJUSTMENT_IN if adjustment.document_type.inventory_behavior == "IN" else MovementType.ADJUSTMENT_OUT
        if any(m.movement_type != expected for m in originals): raise InventoryException("La historia del ajuste es inconsistente.")
        reversal_type = MovementType.RETURN_OUT if expected == MovementType.ADJUSTMENT_IN else MovementType.RETURN_IN
        for movement in originals:
            StockMovementReversalService.reverse(movement=movement, reversal_type=reversal_type, user=user)
        return DocumentService.cancel(adjustment, user=user)
