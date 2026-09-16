from inventory.services.inventory_adjustment_confirmation_service import InventoryAdjustmentConfirmationService
class ConfirmInventoryAdjustment:
    @staticmethod
    def execute(adjustment_id, user=None): return InventoryAdjustmentConfirmationService.confirm(adjustment_id, user=user)
