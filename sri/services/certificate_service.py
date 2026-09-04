from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12


@dataclass
class CertificateData:
    """
    Datos obtenidos desde un certificado PKCS#12.
    """

    private_key: object
    certificate: x509.Certificate
    additional_certificates: tuple


class CertificateService:
    """
    Servicio responsable de cargar, inspeccionar y validar
    certificados electrónicos PKCS#12.

    Este servicio no firma documentos XML.
    """

    @staticmethod
    def load(
        certificate_data,
        password,
    ):
        """
        Carga un certificado PKCS#12 desde bytes.

        Retorna CertificateData con:

        - clave privada
        - certificado principal
        - certificados adicionales
        """

        if not certificate_data:
            raise ValueError(
                "El contenido del certificado no puede estar vacío."
            )

        if not password:
            raise ValueError(
                "La contraseña del certificado es obligatoria."
            )

        if isinstance(password, str):
            password = password.encode("utf-8")

        try:
            (
                private_key,
                certificate,
                additional_certificates,
            ) = pkcs12.load_key_and_certificates(
                certificate_data,
                password,
            )
        except Exception as exc:
            raise ValueError(
                "No se pudo cargar el certificado PKCS#12."
            ) from exc

        if private_key is None:
            raise ValueError(
                "El certificado PKCS#12 no contiene "
                "una clave privada."
            )

        if certificate is None:
            raise ValueError(
                "El certificado PKCS#12 no contiene "
                "un certificado digital."
            )

        return CertificateData(
            private_key=private_key,
            certificate=certificate,
            additional_certificates=tuple(
                additional_certificates or ()
            ),
        )

    @staticmethod
    def load_from_file(
        file_path,
        password,
    ):
        """
        Carga un certificado PKCS#12 desde un archivo.
        """

        try:
            with open(file_path, "rb") as certificate_file:
                certificate_data = certificate_file.read()
        except OSError as exc:
            raise ValueError(
                "No fue posible leer el archivo "
                "del certificado PKCS#12."
            ) from exc

        return CertificateService.load(
            certificate_data=certificate_data,
            password=password,
        )

    @staticmethod
    def get_certificate_subject(
        certificate,
    ):
        """
        Obtiene el subject completo del certificado.
        """

        return certificate.subject.rfc4514_string()

    @staticmethod
    def get_certificate_serial_number(
        certificate,
    ):
        """
        Obtiene el número de serie del certificado.
        """

        return certificate.serial_number

    @staticmethod
    def get_certificate_pem(
        certificate,
    ):
        """
        Convierte el certificado a formato PEM.
        """

        return certificate.public_bytes(
            serialization.Encoding.PEM,
        )

    @staticmethod
    def get_certificate_not_valid_before(
        certificate,
    ):
        """
        Obtiene la fecha UTC desde la cual
        el certificado es válido.
        """

        return certificate.not_valid_before_utc

    @staticmethod
    def get_certificate_not_valid_after(
        certificate,
    ):
        """
        Obtiene la fecha UTC hasta la cual
        el certificado es válido.
        """

        return certificate.not_valid_after_utc

    @staticmethod
    def is_certificate_valid(
        certificate,
    ):
        """
        Verifica si el certificado está vigente
        en la fecha y hora actual.
        """

        now = datetime.now(
            timezone.utc
        )

        not_valid_before = (
            certificate.not_valid_before_utc
        )

        not_valid_after = (
            certificate.not_valid_after_utc
        )

        return (
            not_valid_before
            <= now
            <= not_valid_after
        )

    @staticmethod
    def validate_certificate(
        certificate,
    ):
        """
        Valida que el certificado esté vigente.

        Lanza ValueError si todavía no es válido
        o si ya expiró.
        """

        now = datetime.now(
            timezone.utc
        )

        not_valid_before = (
            certificate.not_valid_before_utc
        )

        not_valid_after = (
            certificate.not_valid_after_utc
        )

        if now < not_valid_before:
            raise ValueError(
                "El certificado todavía no es válido."
            )

        if now > not_valid_after:
            raise ValueError(
                "El certificado electrónico está expirado."
            )

        return True