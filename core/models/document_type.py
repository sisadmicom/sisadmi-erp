from django.db import models
from django.db.models import Q

from core.constants.document_category import DocumentCategory
from core.constants.inventory_behavior import InventoryBehavior
from core.models.base import BaseModel


class DocumentType(BaseModel):
    """
    Define la identidad y las capacidades estructurales
    de un tipo documental SISADMI.

    No ejecuta lógica de inventario, contabilidad ni SRI.
    """

    code = models.CharField(
        max_length=50,
        unique=True,
    )

    name = models.CharField(
        max_length=100,
    )

    category = models.CharField(
        max_length=20,
        choices=DocumentCategory.choices,
    )

    requires_detail = models.BooleanField(
        default=False,
    )

    affects_inventory = models.BooleanField(
        default=False,
    )

    inventory_behavior = models.CharField(
        max_length=20,
        choices=InventoryBehavior.choices,
        default=InventoryBehavior.NONE,
    )

    can_issue_electronic = models.BooleanField(
        default=False,
    )

    class Meta:
        ordering = ["category", "code"]
        verbose_name = "Tipo de documento"
        verbose_name_plural = "Tipos de documento"

        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(affects_inventory=True)
                    | Q(
                        inventory_behavior=InventoryBehavior.NONE
                    )
                ),
                name="document_type_inventory_behavior_consistent",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"
