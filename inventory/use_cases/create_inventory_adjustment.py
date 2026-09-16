from inventory.services.inventory_adjustment_creator import InventoryAdjustmentCreator
class CreateInventoryAdjustment:
    @staticmethod
    def create_in(dto): return InventoryAdjustmentCreator.create(dto, "IN")
    @staticmethod
    def create_out(dto): return InventoryAdjustmentCreator.create(dto, "OUT")
