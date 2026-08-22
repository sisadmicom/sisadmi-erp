# core/exceptions/validation.py

from .base import BusinessException


class ValidationException(BusinessException):
    default_message = "Error de validación."


class InvalidQuantity(ValidationException):
    default_message = "Cantidad inválida."


class InvalidPrice(ValidationException):
    default_message = "Precio inválido."