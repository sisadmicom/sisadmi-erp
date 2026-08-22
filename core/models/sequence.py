from django.db import models
from django.conf import settings

from core.models.base import BaseModel
from .company import Company
from .branch import Branch


class Sequence(BaseModel):

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT
    )

    code = models.CharField(
        max_length=30
    )

    name = models.CharField(
        max_length=100
    )

    prefix = models.CharField(
        max_length=10
    )

    series = models.CharField(
        max_length=10,
        default="001"
    )

    next_number = models.PositiveIntegerField(
        default=1
    )

    padding = models.PositiveIntegerField(
        default=6
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "branch", "code"],
                name="unique_sequence_company_branch_code"
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.prefix}-{self.series}"