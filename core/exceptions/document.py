# core/exceptions/document.py

from .base import BusinessException


class DocumentException(BusinessException):
    default_message = "Error en el documento."


class DocumentAlreadyConfirmed(DocumentException):
    default_message = "El documento ya fue confirmado."


class DocumentCancelled(DocumentException):
    default_message = "El documento está anulado."


class EmptyDocument(DocumentException):
    default_message = "El documento no tiene detalles."