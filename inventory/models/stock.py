from django.db import models
from core.models.base import BaseModel

from core.models import Company
from core.models import Branch

from catalog.models import Product

from .warehouse import Warehouse


class Stock(BaseModel):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE
    )

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    reserved_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )


    @property
    def available_quantity(self):

        return self.quantity - self.reserved_quantity


    class Meta:

        constraints = [

            models.UniqueConstraint(

                fields=[

                    "company",

                    "branch",

                    "warehouse",

                    "product"

                ],

                name="unique_stock"

            )

        ]


    def __str__(self):

        return f"{self.product} ({self.quantity})"