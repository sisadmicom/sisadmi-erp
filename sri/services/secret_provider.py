from abc import ABC, abstractmethod


class SecretProvider(ABC):
    """
    Contrato para obtener secretos utilizados por SISADMI.

    Las implementaciones concretas determinan dónde
    se almacenan físicamente los secretos.
    """

    @abstractmethod
    def get(self, key):
        raise NotImplementedError
