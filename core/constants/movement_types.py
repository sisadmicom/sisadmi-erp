from django.db import models


class MovementTypes(models.TextChoices):
    PURCHASE = "PURCHASE", "Compra"
    SALE = "SALE", "Venta"
    TRANSFER_IN = "TRANSFER_IN", "Transferencia Entrada"
    TRANSFER_OUT = "TRANSFER_OUT", "Transferencia Salida"
    ADJUSTMENT_IN = "ADJUSTMENT_IN", "Ajuste Entrada"
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT", "Ajuste Salida"