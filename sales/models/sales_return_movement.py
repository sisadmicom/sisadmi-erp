from django.db import models


class SalesReturnMovement(models.Model):
    """Identity of each RETURN_IN effect owned by a SalesReturn."""

    sales_return = models.ForeignKey(
        "sales.SalesReturn",
        on_delete=models.PROTECT,
        related_name="movement_manifest",
    )
    stock_movement = models.OneToOneField(
        "inventory.StockMovement",
        on_delete=models.PROTECT,
        related_name="sales_return_movement_manifest",
    )
