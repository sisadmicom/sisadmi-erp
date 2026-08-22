from django.db import models

from core.models.base import BaseModel
from core.models import Company


class Tax(BaseModel):

    TAX_TYPES = (
        ("IVA", "IVA"),
        ("ICE", "ICE"),
        ("OTHER", "Otro"),
    )

    name = models.CharField(
        max_length=100
    )

    code = models.CharField(
        max_length=30
    )

    tax_type = models.CharField(
        max_length=20,
        choices=TAX_TYPES
    )

    rate = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=0
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="taxes"
    )

    is_active = models.BooleanField(
        default=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"],
                name="unique_tax_company_code"
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.name} ({self.rate}%)"