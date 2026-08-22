# core/exceptions/inventory.py

from .base import BusinessException


class InventoryException(BusinessException):
    default_message = "Error de inventario."


class InsufficientStock(InventoryException):
    default_message = "Stock insuficiente."


class NegativeStock(InventoryException):
    default_message = "El stock no puede ser negativo."