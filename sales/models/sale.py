from decimal import Decimal

from django.db import models

from core.models import BaseDocument

from people.models import Customer
from inventory.models import Warehouse


class Sale(BaseDocument):

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="sales",
    )

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="sales",
    )

    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        ordering = ["-id"]
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"

    def __str__(self):
        return f"{self.number} - {self.customer}"