#core/constants/document_status.py
from django.db import models
class DocumentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    PENDING = "PENDING", "Pendiente"
    CONFIRMED = "CONFIRMED", "Confirmado"
    CLOSED = "CLOSED", "Cerrado"
    CANCELLED = "CANCELLED", "Anulado"