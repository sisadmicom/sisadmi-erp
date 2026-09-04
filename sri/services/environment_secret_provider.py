import os

from sri.services.secret_provider import SecretProvider


class EnvironmentSecretProvider(SecretProvider):
    """
    Obtiene secretos desde variables de entorno.

    Esta implementación permite mantener credenciales
    sensibles fuera del código fuente y de la base de datos.
    """

    def get(self, key):

        if not key:
            raise ValueError(
                "La clave del secreto es obligatoria."
            )

        value = os.environ.get(key)

        if value is None:
            raise ValueError(
                f"No existe el secreto configurado: {key}"
            )

        return value
