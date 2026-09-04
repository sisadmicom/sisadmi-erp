import os
from unittest.mock import patch

from django.test import SimpleTestCase

from sri.services.environment_secret_provider import (
    EnvironmentSecretProvider,
)
from sri.services.secret_provider import SecretProvider


class SecretProviderTest(SimpleTestCase):

    def test_secret_provider_is_abstract(self):

        with self.assertRaises(TypeError):
            SecretProvider()

    def test_environment_secret_provider_returns_value(self):

        provider = EnvironmentSecretProvider()

        with patch.dict(
            os.environ,
            {
                "SISADMI_TEST_SECRET": "secret-value",
            },
            clear=False,
        ):

            result = provider.get(
                "SISADMI_TEST_SECRET"
            )

        self.assertEqual(
            result,
            "secret-value",
        )

    def test_environment_secret_provider_rejects_empty_key(self):

        provider = EnvironmentSecretProvider()

        with self.assertRaisesMessage(
            ValueError,
            "La clave del secreto es obligatoria.",
        ):

            provider.get("")

    def test_environment_secret_provider_rejects_none_key(self):

        provider = EnvironmentSecretProvider()

        with self.assertRaisesMessage(
            ValueError,
            "La clave del secreto es obligatoria.",
        ):

            provider.get(None)

    def test_environment_secret_provider_rejects_missing_secret(self):

        provider = EnvironmentSecretProvider()

        with patch.dict(
            os.environ,
            {},
            clear=True,
        ):

            with self.assertRaisesMessage(
                ValueError,
                (
                    "No existe el secreto configurado: "
                    "SISADMI_MISSING_SECRET"
                ),
            ):

                provider.get(
                    "SISADMI_MISSING_SECRET"
                )
