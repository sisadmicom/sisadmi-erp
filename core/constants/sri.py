class SriEnvironment:
    TEST = "1"
    PRODUCTION = "2"

    CHOICES = (
        (TEST, "Pruebas"),
        (PRODUCTION, "Producción"),
    )


class SriEmissionType:
    NORMAL = "1"

    CHOICES = (
        (NORMAL, "Emisión normal"),
    )

class SriDocumentType:
    INVOICE = "01"
    CREDIT_NOTE = "04"
    DEBIT_NOTE = "05"
    WITHHOLDING = "07"
    PURCHASE_SETTLEMENT = "03"
    DELIVERY_NOTE = "06"

    CHOICES = (
        (INVOICE, "Factura"),
        (CREDIT_NOTE, "Nota de crédito"),
        (DEBIT_NOTE, "Nota de débito"),
        (WITHHOLDING, "Comprobante de retención"),
        (PURCHASE_SETTLEMENT, "Liquidación de compra"),
        (DELIVERY_NOTE, "Guía de remisión"),
    )