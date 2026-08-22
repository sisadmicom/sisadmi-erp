# core/exceptions/erp_exception.py

class ERPException(Exception):
    """
    Excepción base del ERP.
    """
    default_code = "ERP_ERROR"

    def __init__(self, message, code=None):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code