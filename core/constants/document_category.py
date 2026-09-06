from django.db import models


class DocumentCategory(models.TextChoices):
    SALES = "SALES", "Ventas"
    PURCHASES = "PURCHASES", "Compras"
    INVENTORY = "INVENTORY", "Inventario"
    ACCOUNTING = "ACCOUNTING", "Contabilidad"
    PRODUCTION = "PRODUCTION", "Producción"
    PAYROLL = "PAYROLL", "Nómina"
