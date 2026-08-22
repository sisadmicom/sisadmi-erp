from django.db import models

from core.models.base import BaseModel


class BaseDetail(BaseModel):

    line = models.PositiveIntegerField()

    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
    )

    unit_price = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0
    )

    discount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    subtotal = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    tax_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    total = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    class Meta:
        abstract = True