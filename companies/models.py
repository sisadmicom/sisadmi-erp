from django.db import models
from people.models import Person


class Company(models.Model):

    person = models.OneToOneField(
        Person,
        on_delete=models.CASCADE
    )

    trade_name = models.CharField(
        max_length=200
    )

    is_active = models.BooleanField(
        default=True
    )

    def __str__(self):
        return self.trade_name