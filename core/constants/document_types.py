class DocumentTypes:
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER = "TRANSFER"

    CHOICES = (
        (PURCHASE, "Compra"),
        (SALE, "Venta"),
        (ADJUSTMENT, "Ajuste"),
        (TRANSFER, "Transferencia"),
    )