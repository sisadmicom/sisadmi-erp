# core/exceptions/base.py

class BusinessException(Exception):
    """
    Excepción base para todo el ERP.
    """

    default_message = "Ha ocurrido un error de negocio."

    def __init__(self, message=None):
        super().__init__(message or self.default_message)