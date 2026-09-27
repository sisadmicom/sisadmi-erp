from django.db import models


class SriReceptionAttemptStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "En progreso"
    RECEIVED = "RECEIVED", "Recibido"
    REJECTED = "REJECTED", "Rechazado"
    UNCERTAIN = "UNCERTAIN", "Resultado incierto"
    FAILED = "FAILED", "Fallido"
