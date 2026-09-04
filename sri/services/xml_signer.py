from abc import ABC, abstractmethod


class XmlSigner(ABC):
    """
    Interfaz para los firmadores electrónicos de XML.

    XmlSigningService no debe conocer:
    - certificados
    - archivos .p12/.pfx
    - contraseñas
    - librerías criptográficas
    - implementación XAdES

    Solo conoce esta interfaz.
    """

    @abstractmethod
    def sign(self, xml):
        """
        Recibe XML sin firmar y devuelve XML firmado.
        """
        raise NotImplementedError
