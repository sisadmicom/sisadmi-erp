class DocumentError(Exception):
    """Excepción base para documentos."""


class InvalidDocumentState(DocumentError):
    """Estado inválido del documento."""


class DocumentWithoutDetails(DocumentError):
    """El documento no posee detalles."""


class InvalidQuantity(DocumentError):
    """Cantidad inválida."""


class InvalidPrice(DocumentError):
    """Precio inválido."""