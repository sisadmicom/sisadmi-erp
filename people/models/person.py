from django.db import models

from core.models import BaseModel

from people.models.geography import (
    Country,
    Province,
    Canton,
    Parish
)


class Person(BaseModel):

    PERSON_TYPES=(
        ("NATURAL","Natural"),
        ("LEGAL","Jurídica")
    )

    identification=models.CharField(
        max_length=20,
        unique=True
    )

    person_type=models.CharField(
        max_length=10,
        choices=PERSON_TYPES
    )

    full_name=models.CharField(
        max_length=250
    )

    email=models.EmailField(
        blank=True,
        null=True
    )

    phone=models.CharField(
        max_length=30,
        blank=True
    )

    country=models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        null=True
    )

    province=models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        null=True
    )

    canton=models.ForeignKey(
        Canton,
        on_delete=models.PROTECT,
        null=True
    )

    parish=models.ForeignKey(
        Parish,
        on_delete=models.PROTECT,
        null=True
    )

    address=models.TextField(
        blank=True
    )

    def __str__(self):
        return f"{self.identification} - {self.full_name}"