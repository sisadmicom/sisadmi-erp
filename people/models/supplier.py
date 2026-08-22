from django.db import models
from people.models import Person
from core.models.base import BaseModel

class Supplier(BaseModel):

    person=models.OneToOneField(
        Person,
        on_delete=models.CASCADE
    )

    notes=models.TextField(
        blank=True
    )

    def __str__(self):
        return self.person.full_name