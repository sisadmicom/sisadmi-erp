# catalog/models/brand.py
from django.db import models

from core.models.base import BaseModel


class Brand(BaseModel):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    def __str__(self):
        return self.name