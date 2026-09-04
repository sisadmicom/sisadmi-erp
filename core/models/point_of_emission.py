#core/models/point_of_emission.py
from django.db import models

from core.models.base import BaseModel
from .branch import Branch


class PointOfEmission(BaseModel):

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="points_of_emission",
    )

    code = models.CharField(
        max_length=3,
    )

    name = models.CharField(
        max_length=100,
    )

    address = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "code"],
                name="unique_point_emission_branch_code",
            ),
        ]

        ordering = ["branch", "code"]

        verbose_name = "Punto de emisión"
        verbose_name_plural = "Puntos de emisión"

    def __str__(self):
        return f"{self.branch.code}-{self.code} - {self.name}"