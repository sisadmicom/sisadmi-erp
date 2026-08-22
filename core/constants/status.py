class DocumentStatus:
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"

    CHOICES = (
        (DRAFT, "Borrador"),
        (CONFIRMED, "Confirmado"),
        (CANCELLED, "Anulado"),
    )