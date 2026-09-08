# sales/models/sale_detail.py

from django.db import models

from core.models import BaseDocumentLine, QuantityLineMixin, CommercialAmountsMixin
from catalog.models import Product

from .sale import Sale


class SaleDetail(BaseDocumentLine, QuantityLineMixin, CommercialAmountsMixin):

    sale = models.ForeignKey(
        Sale,
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
        return f"{self.sale.number} - {self.product.name}"