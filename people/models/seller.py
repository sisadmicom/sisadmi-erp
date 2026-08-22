from django.db import models

from people.models import Employee


class Seller(models.Model):

    employee=models.OneToOneField(
        Employee,
        on_delete=models.CASCADE
    )

    commission=models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )