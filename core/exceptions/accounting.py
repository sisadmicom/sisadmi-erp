# core/exceptions/accounting.py

from .base import BusinessException


class AccountingException(BusinessException):
    default_message = "Error contable."