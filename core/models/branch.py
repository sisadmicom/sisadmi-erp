from django.db import models

from core.models.base import BaseModel
from .company import Company


class Branch(BaseModel):

    company=models.ForeignKey(
        Company,
        on_delete=models.CASCADE
    )

    code=models.CharField(
        max_length=20,blank=True,null=True
    )

    name=models.CharField(
        max_length=100
    )

    address=models.TextField(
        blank=True
    )

    is_main=models.BooleanField(
        default=False
    )


    def __str__(self):

        return self.name