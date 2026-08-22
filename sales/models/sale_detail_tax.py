from django.db import models

from core.models import BaseModel
from catalog.models import Tax

from .sale_detail import SaleDetail


class SaleDetailTax(BaseModel):

    detail = models.ForeignKey(
        SaleDetail,
        related_name="applied_taxes",
        on_delete=models.CASCADE,
    )

    tax = models.ForeignKey(
        Tax,
        on_delete=models.PROTECT,
    )

    tax_code = models.CharField(
        max_length=30,
    )

    tax_name = models.CharField(
        max_length=100,
    )

    tax_type = models.CharField(
        max_length=20,
    )

    rate = models.DecimalField(
        max_digits=8,
        decimal_places=4,
    )

    base = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )

    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return (
            f"{self.detail} - "
            f"{self.tax_code} - "
            f"{self.amount}"
        )
