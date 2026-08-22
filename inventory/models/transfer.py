from django.db import models

from core.models import BaseDocument

from .warehouse import Warehouse


class Transfer(BaseDocument):

    source_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="transfers_out",
    )

    destination_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="transfers_in",
    )

    class Meta:
        ordering = ["-id"]
        verbose_name = "Transferencia"
        verbose_name_plural = "Transferencias"

    def __str__(self):
        return (
            f"{self.number} - "
            f"{self.source_warehouse.name} -> "
            f"{self.destination_warehouse.name}"
        )
