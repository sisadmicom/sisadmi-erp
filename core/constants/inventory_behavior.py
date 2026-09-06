from django.db import models


class InventoryBehavior(models.TextChoices):
    NONE = "NONE", "No afecta inventario"
    IN = "IN", "Entrada"
    OUT = "OUT", "Salida"
    TRANSFER = "TRANSFER", "Transferencia"
    TRANSFORM = "TRANSFORM", "Transformación"
