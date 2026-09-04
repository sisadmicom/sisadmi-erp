import tempfile
from unittest.mock import Mock, patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from core.models import Company
from people.models import Person
from sri.models import SriCertificate
from sri.services.sri_signer_factory import SriSignerFactory


class SriSignerFactoryTest(TestCase):

    def setUp(self):

        self.private_directory = tempfile.TemporaryDirectory()

        self.override_settings = override_settings(
            SRI_PRIVATE_STORAGE_ROOT=self.private_directory.name
        )

        self.override_settings.enable()

        company_person = Person.objects.create(
            identification="1790000001001",
            person_type="LEGAL",
            full_name="Empresa Test",
        )

        self.company = Company.objects.create(
            person=company_person,
            commercial_name="Empresa Test",
        )

        self.secret_provider = Mock()
        self.certificate_service = Mock()

        self.factory = SriSignerFactory(
            secret_provider=self.secret_provider,
            certificate_service=self.certificate_service,
        )

    def tearDown(self):

        self.override_settings.disable()
        self.private_directory.cleanup()

    def create_certificate(
        self,
        *,
        is_default=True,
        is_active=True,
        secret_key="SRI_CERTIFICATE_PASSWORD",
    ):

        certificate = SriCertificate.objects.create(
            company=self.company,
            secret_key=secret_key,
            is_default=is_default,
            is_active=is_active,
        )

        certificate.certificate_file.save(
            "certificate.p12",
            ContentFile(b"pkcs12-test-content"),
        )

        return certificate

    def test_gets_active_default_certificate_for_company(self):

        certificate = self.create_certificate()

        result = self.factory.get_certificate(
            self.company
        )

        self.assertEqual(
            result,
            certificate,
        )

    def test_raises_error_when_company_has_no_active_default_certificate(self):

        self.create_certificate(
            is_default=False
        )

        with self.assertRaisesMessage(
            ValueError,
            "La empresa no tiene un certificado SRI activo y predeterminado.",
        ):

            self.factory.get_certificate(
                self.company
            )

    def test_ignores_inactive_default_certificate(self):

        self.create_certificate(
            is_default=True,
            is_active=False,
        )

        with self.assertRaisesMessage(
            ValueError,
            "La empresa no tiene un certificado SRI activo y predeterminado.",
        ):

            self.factory.get_certificate(
                self.company
            )

    @patch(
        "sri.services.sri_signer_factory.Pkcs12XmlSigner"
    )
    def test_create_signer_loads_certificate_and_secret(
        self,
        signer_class,
    ):

        self.create_certificate(
            secret_key="COMPANY_SRI_PASSWORD",
        )

        self.secret_provider.get.return_value = (
            "certificate-password"
        )

        certificate_data = Mock()

        self.certificate_service.load.return_value = (
            certificate_data
        )

        signer = Mock()
        signer_class.return_value = signer

        result = self.factory.create_for_company(
            self.company
        )

        self.secret_provider.get.assert_called_once_with(
            "COMPANY_SRI_PASSWORD"
        )

        self.certificate_service.load.assert_called_once_with(
            b"pkcs12-test-content",
            "certificate-password",
        )

        signer_class.assert_called_once_with(
            certificate_data
        )

        self.assertIs(
            result,
            signer,
        )

    def test_create_signer_requires_certificate_file(self):

        SriCertificate.objects.create(
            company=self.company,
            secret_key="SRI_CERTIFICATE_PASSWORD",
            is_default=True,
            is_active=True,
        )

        with self.assertRaisesMessage(
            ValueError,
            "El certificado SRI no tiene un archivo PKCS#12 configurado.",
        ):

            self.factory.create_for_company(
                self.company
            )
