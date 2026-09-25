from django.db import models


class InventoryAdjustmentMovement(models.Model):
    inventory_adjustment = models.ForeignKey(
        "inventory.InventoryAdjustment",
        on_delete=models.PROTECT,
        related_name="movement_manifest",
    )
    stock_movement = models.OneToOneField(
        "inventory.StockMovement",
        on_delete=models.PROTECT,
        related_name="inventory_adjustment_movement_manifest",
    )
