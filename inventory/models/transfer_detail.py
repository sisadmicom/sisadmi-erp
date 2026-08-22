from django.db import models

from core.models.base_detail import BaseDetail

from catalog.models import Product

from .transfer import Transfer


class TransferDetail(BaseDetail):

    transfer = models.ForeignKey(
        Transfer,
        related_name="details",
        on_delete=models.CASCADE,
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return (
            f"{self.transfer.number} - "
            f"{self.product.name}"
        )
