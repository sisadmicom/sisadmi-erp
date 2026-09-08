from django.db import models


class QuantityLineMixin(models.Model):
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
    )

    class Meta:
        abstract = True
