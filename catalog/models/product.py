# catalog/models/product.py

from django.db import models

from core.models.base import BaseModel

from .group import ProductGroup
from .subgroup import ProductSubGroup
from .brand import Brand
from .unit import UnitMeasure
from core.models import Company
from .tax import Tax

class Product(BaseModel):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE
    )

    code = models.CharField(
        max_length=30
    )

    barcode = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    name = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    group = models.ForeignKey(
        ProductGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    subgroup = models.ForeignKey(
        ProductSubGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    unit_measure = models.ForeignKey(
        UnitMeasure,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    taxes = models.ManyToManyField(
        Tax,
        blank=True,
        related_name="products"
    )

    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    sale_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    is_service = models.BooleanField(
        default=False
    )

    stock_control = models.BooleanField(
        default=True
    )

    class Meta:

        constraints = [

            models.UniqueConstraint(
                fields=["company", "code"],
                name="unique_product_company_code"
            )

        ]

    def __str__(self):
        return f"{self.code} - {self.name}"