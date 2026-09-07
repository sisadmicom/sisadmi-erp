from django.db import models
from django.conf import settings

from core.models.base import BaseModel
from .company import Company
from .branch import Branch
from .document_type import DocumentType


class Sequence(BaseModel):

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT
    )

    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        related_name="sequences",
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
                fields=["company", "branch", "document_type"],
                name="unique_sequence_company_branch_document_type",
            )
        ]

    def __str__(self):
        return f"{self.document_type.code} - {self.prefix}{self.series}"