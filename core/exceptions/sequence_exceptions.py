class SequenceError(Exception):
    """Excepción base de secuencias."""


class SequenceNotFound(SequenceError):
    """La secuencia no existe."""


class SequenceInactive(SequenceError):
    """La secuencia está inactiva."""