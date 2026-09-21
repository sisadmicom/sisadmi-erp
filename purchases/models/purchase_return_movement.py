from django.db import models


class PurchaseReturnMovement(models.Model):
    """Identidad de cada salida original; su historia reside en StockMovement."""

    purchase_return = models.ForeignKey(
        "purchases.PurchaseReturn", on_delete=models.PROTECT, related_name="movement_manifest",
    )
    stock_movement = models.OneToOneField("inventory.StockMovement", on_delete=models.PROTECT)
