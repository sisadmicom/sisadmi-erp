from django.db import models

from core.models.base import BaseModel
from core.models import Company
from .tax import Tax


class TaxConfiguration(BaseModel):

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="tax_configuration"
    )

    taxes = models.ManyToManyField(
        Tax,
        blank=True,
        related_name="global_configurations"
    )

    def __str__(self):
        return f"Configuración de impuestos - {self.company}"