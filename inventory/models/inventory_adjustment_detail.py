from django.db import models

from core.models import BaseDocumentLine, QuantityLineMixin
from catalog.models import Product
from .inventory_adjustment import InventoryAdjustment


class InventoryAdjustmentDetail(BaseDocumentLine, QuantityLineMixin):
    adjustment = models.ForeignKey(InventoryAdjustment, related_name="details", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["adjustment", "line"], name="unique_adjustment_line"),
            models.UniqueConstraint(fields=["adjustment", "product"], name="unique_adjustment_product"),
        ]
        ordering = ["line"]
