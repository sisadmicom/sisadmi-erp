# purchases/models/purchase.py

from django.db import models

from core.models import BaseDocument

from core.models import Company, Branch

from people.models import Supplier


class Purchase(BaseDocument):

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT
    )

    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.number