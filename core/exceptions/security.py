# core/exceptions/security.py

from .base import BusinessException


class SecurityException(BusinessException):
    default_message = "Acceso denegado."