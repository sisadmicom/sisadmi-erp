from django.db import models


class CommercialAmountsMixin(models.Model):
    unit_price = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0
    )

    discount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    subtotal = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    tax_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    total = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    class Meta:
        abstract = True
