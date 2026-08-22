#catalog/models/subgroup.py
from django.db import models

from core.models.base import BaseModel
from core.models import Company

from .group import ProductGroup
from .tax import Tax

class ProductSubGroup(BaseModel):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    group = models.ForeignKey(
        ProductGroup,
        on_delete=models.CASCADE
    )

    name = models.CharField(
        max_length=100
    )

    taxes = models.ManyToManyField(
        Tax,
        blank=True,
        related_name="product_subgroups"
    )

    class Meta:

        constraints = [

            models.UniqueConstraint(
                fields=["company", "group", "name"],
                name="unique_subgroup_company"
            )

        ]

    def __str__(self):

        return self.name