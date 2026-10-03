from django.db import models


class PaymentMethod(models.TextChoices):
    NON_FINANCIAL = "NON_FINANCIAL", "Sin sistema financiero"
    DEBT_OFFSET = "DEBT_OFFSET", "Compensación de deudas"
    DEBIT_CARD = "DEBIT_CARD", "Tarjeta de débito"
    ELECTRONIC_MONEY = "ELECTRONIC_MONEY", "Dinero electrónico"
    PREPAID_CARD = "PREPAID_CARD", "Tarjeta prepago"
    CREDIT_CARD = "CREDIT_CARD", "Tarjeta de crédito"
    FINANCIAL_OTHER = "FINANCIAL_OTHER", "Otro medio financiero"
    TITLE_ENDORSEMENT = "TITLE_ENDORSEMENT", "Endoso de títulos"
