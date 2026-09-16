from inventory.services.inventory_adjustment_cancellation_service import InventoryAdjustmentCancellationService
class CancelInventoryAdjustment:
    @staticmethod
    def execute(adjustment_id, user=None): return InventoryAdjustmentCancellationService.cancel(adjustment_id, user=user)
