from django.db import models

from core.models.base import BaseModel
from people.models import Person


class Company(BaseModel):

    person = models.OneToOneField(
        Person,
        on_delete=models.CASCADE
    )

    commercial_name=models.CharField(
        max_length=200,null=True
    )

    logo=models.ImageField(
        upload_to="company",
        blank=True,
        null=True
    )


    def __str__(self):

        return self.commercial_name