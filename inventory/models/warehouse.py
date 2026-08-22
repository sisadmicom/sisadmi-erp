from django.db import models

from core.models.base import BaseModel

from core.models import Company
from core.models import Branch


class Warehouse(BaseModel):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE
    )

    code = models.CharField(
        max_length=20
    )

    name = models.CharField(
        max_length=100
    )

    address = models.TextField(
        blank=True,
        null=True
    )

    is_main = models.BooleanField(
        default=False
    )


    class Meta:

        constraints = [

            models.UniqueConstraint(

                fields=[
                    "company",
                    "branch",
                    "code"
                ],

                name="unique_warehouse"

            )

        ]

        ordering = ["name"]


    def __str__(self):

        return f"{self.branch} - {self.name}"