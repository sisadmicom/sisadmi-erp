from django.db import models


class MovementType(models.TextChoices):

    PURCHASE = "PURCHASE", "Compra"
    SALE = "SALE", "Venta"

    TRANSFER_IN = "TRANSFER_IN", "Transferencia Entrada"
    TRANSFER_OUT = "TRANSFER_OUT", "Transferencia Salida"

    ADJUSTMENT_IN = "ADJUSTMENT_IN", "Ajuste Entrada"
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT", "Ajuste Salida"

    RETURN_IN = "RETURN_IN", "Devolución Entrada"
    RETURN_OUT = "RETURN_OUT", "Devolución Salida"

    PRODUCTION_IN = "PRODUCTION_IN", "Producción Entrada"
    PRODUCTION_OUT = "PRODUCTION_OUT", "Producción Consumo"

    @classmethod
    def is_input(cls, movement_type):
        return movement_type in {
            cls.PURCHASE,
            cls.TRANSFER_IN,
            cls.ADJUSTMENT_IN,
            cls.RETURN_IN,
            cls.PRODUCTION_IN,
        }

    @classmethod
    def is_output(cls, movement_type):
        return movement_type in {
            cls.SALE,
            cls.TRANSFER_OUT,
            cls.ADJUSTMENT_OUT,
            cls.RETURN_OUT,
            cls.PRODUCTION_OUT,
        }