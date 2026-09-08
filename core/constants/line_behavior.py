from django.db import models


class LineBehavior(models.TextChoices):
    NONE = "NONE", "Sin líneas"
    QUANTITY = "QUANTITY", "Cantidad"
    VALUED = "VALUED", "Valorada"
    COMMERCIAL = "COMMERCIAL", "Comercial"
