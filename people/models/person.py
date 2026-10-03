import re

from django.core.exceptions import ValidationError
from django.db import models

from people.constants.identification_type import IdentificationType

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

    identification_type = models.CharField(
        max_length=20,
        choices=IdentificationType.choices,
        null=True,
        blank=True,
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

    def clean(self):
        super().clean()
        widths = {IdentificationType.RUC: 13, IdentificationType.CEDULA: 10}
        width = widths.get(self.identification_type)
        if width is not None and re.fullmatch(r"[0-9]{%d}" % width, self.identification or "") is None:
            raise ValidationError({"identification": f"La identificación debe contener {width} dígitos."})

    def __str__(self):
        return f"{self.identification} - {self.full_name}"