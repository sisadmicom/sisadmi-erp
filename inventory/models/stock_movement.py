from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from django.db import models

from core.models.base import BaseModel
from core.models import Company, Branch

from catalog.models import Product

from inventory.constants.movement_type import MovementType

from .warehouse import Warehouse


class StockMovement(BaseModel):
    """
    Registro histórico de movimientos de inventario.

    Todo cambio de existencias debe generar un StockMovement.

    Este modelo no modifica inventario.
    Solo registra el movimiento realizado.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    movement_type = models.CharField(
        max_length=30,
        choices=MovementType.choices,
    )

    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    movement_date = models.DateTimeField(
        auto_now_add=True,
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    object_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    document = GenericForeignKey(
        "content_type",
        "object_id",
    )

    notes = models.TextField(
        blank=True,
        default="",
    )

    unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=0,
    )

    class Meta:
        ordering = ["-id"]

        indexes = [
            models.Index(
                fields=[
                    "company",
                    "branch",
                    "warehouse",
                    "product",
                ]
            ),
            models.Index(
                fields=[
                    "movement_date",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_movement_type_display()} | "
            f"{self.product} | "
            f"{self.quantity}"
        )