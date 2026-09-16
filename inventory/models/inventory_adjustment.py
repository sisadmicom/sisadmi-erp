from django.db import models

from core.models import BaseDocument
from .warehouse import Warehouse


class InventoryAdjustment(BaseDocument):
    DOCUMENT_TYPE_CODES = {
        "IN": "INVENTORY_ADJUSTMENT_IN",
        "OUT": "INVENTORY_ADJUSTMENT_OUT",
    }
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="inventory_adjustments")

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.number} - {self.warehouse.name}"
