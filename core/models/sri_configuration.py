from django.db import models

from core.models.base import BaseModel
from .company import Company


class SriConfiguration(BaseModel):

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="sri_configuration",
    )

    environment = models.CharField(
        max_length=1,
        choices=(
            ("1", "Pruebas"),
            ("2", "Producción"),
        ),
        default="1",
    )

    emission_type = models.CharField(
        max_length=1,
        choices=(
            ("1", "Emisión normal"),
        ),
        default="1",
    )

    accounting_required = models.BooleanField(
        default=False,
    )

    special_taxpayer_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Configuración SRI"
        verbose_name_plural = "Configuraciones SRI"

    def __str__(self):
        return f"SRI - {self.company}"
