from django.db import models

from core.models.base_detail import BaseDetail

from catalog.models import Product

from .purchase import Purchase


class PurchaseDetail(BaseDetail):

    purchase = models.ForeignKey(
        Purchase,
        related_name="details",
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.purchase.number} - {self.product.name}"