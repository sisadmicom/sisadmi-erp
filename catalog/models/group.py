#catalog/models/group.py
from django.db import models

from core.models.base import BaseModel
from core.models import Company
from .tax import Tax

class ProductGroup(BaseModel):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    name = models.CharField(
        max_length=100
    )

    taxes = models.ManyToManyField(
        Tax,
        blank=True,
        related_name="product_groups"
    )

    class Meta:

        constraints = [

            models.UniqueConstraint(
                fields=["company", "name"],
                name="unique_group_company"
            )

        ]

    def __str__(self):

        return self.name