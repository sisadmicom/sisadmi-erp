class SriDocumentStatus:

    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    SIGNED = "SIGNED"
    SENT = "SENT"
    RECEIVED = "RECEIVED"
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"

    CHOICES = (
        (DRAFT, "Borrador"),
        (GENERATED, "XML generado"),
        (SIGNED, "Firmado"),
        (SENT, "Enviado"),
        (RECEIVED, "Recibido"),
        (AUTHORIZED, "Autorizado"),
        (REJECTED, "Rechazado"),
        (CANCELLED, "Cancelado"),
        (ERROR, "Error"),
    )
