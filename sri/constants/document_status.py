from django.db import models


class SriDocumentStatus(models.TextChoices):

    DRAFT = "DRAFT", "Borrador"

    PENDING = "PENDING", "Pendiente"

    GENERATED = "GENERATED", "XML generado"

    SIGNED = "SIGNED", "Firmado"

    SENT = "SENT", "Enviado"

    RECEIVED = "RECEIVED", "Recibido"

    AUTHORIZED = "AUTHORIZED", "Autorizado"

    REJECTED = "REJECTED", "Rechazado"

    ERROR = "ERROR", "Error"
