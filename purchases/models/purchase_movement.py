from django.db import models


class PurchaseMovement(models.Model):
    purchase = models.ForeignKey(
        "purchases.Purchase", on_delete=models.PROTECT, related_name="movement_manifest",
    )
    stock_movement = models.OneToOneField(
        "inventory.StockMovement", on_delete=models.PROTECT, related_name="purchase_movement_manifest",
    )
