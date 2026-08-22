from django.db import models

from people.models import Person
from core.models.base import BaseModel

class Customer(BaseModel):

    person=models.OneToOneField(
        Person,
        on_delete=models.CASCADE
    )

    credit_limit=models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    notes=models.TextField(
        blank=True
    )

    def __str__(self):
        return self.person.full_name