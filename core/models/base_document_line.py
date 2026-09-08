from django.db import models

from core.models.base import BaseModel


class BaseDocumentLine(BaseModel):
    line = models.PositiveIntegerField()

    class Meta:
        abstract = True
