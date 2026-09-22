from django.db import models


class SaleMovement(models.Model):
    sale = models.ForeignKey(
        "sales.Sale", on_delete=models.PROTECT, related_name="movement_manifest",
    )
    stock_movement = models.OneToOneField(
        "inventory.StockMovement", on_delete=models.PROTECT, related_name="sale_movement_manifest",
    )
