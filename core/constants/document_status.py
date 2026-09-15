#core/constants/document_status.py
from django.db import models
class DocumentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    CONFIRMED = "CONFIRMED", "Confirmado"
    CANCELLED = "CANCELLED", "Anulado"