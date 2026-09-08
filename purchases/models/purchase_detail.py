from django.db import models

from core.models import BaseDocumentLine, QuantityLineMixin, CommercialAmountsMixin

from catalog.models import Product

from .purchase import Purchase


class PurchaseDetail(BaseDocumentLine, QuantityLineMixin, CommercialAmountsMixin):

    purchase = models.ForeignKey(
        Purchase,
        related_name="details",
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.purchase.number} - {self.product.name}"