from django.db import models


class IdentificationType(models.TextChoices):
    RUC = "RUC", "RUC"
    CEDULA = "CEDULA", "Cédula"
    PASSPORT = "PASSPORT", "Pasaporte"
    FOREIGN_ID = "FOREIGN_ID", "Identificación del exterior"
