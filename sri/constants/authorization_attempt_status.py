from django.db import models


class SriAuthorizationAttemptStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "En progreso"
    AUTHORIZED = "AUTHORIZED", "Autorizado"
    NOT_AUTHORIZED = "NOT_AUTHORIZED", "No autorizado"
    PENDING = "PENDING", "Pendiente"
    UNCERTAIN = "UNCERTAIN", "Resultado incierto"
    PROTOCOL_ERROR = "PROTOCOL_ERROR", "Error de protocolo"
