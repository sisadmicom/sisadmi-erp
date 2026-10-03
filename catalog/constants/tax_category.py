from django.db import models


class TaxCategory(models.TextChoices):
    VAT_STANDARD = "VAT_STANDARD", "IVA ordinario"
    VAT_ZERO_RATED = "VAT_ZERO_RATED", "IVA tarifa cero"
    VAT_EXEMPT = "VAT_EXEMPT", "Exento de IVA"
    VAT_NOT_SUBJECT = "VAT_NOT_SUBJECT", "No objeto de IVA"
