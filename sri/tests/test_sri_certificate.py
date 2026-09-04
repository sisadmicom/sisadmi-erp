import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.test import TestCase, override_settings

from core.models import Company
from people.models import Person
from sri.models import SriCertificate


class SriCertificateTest(TestCase):

    def setUp(self):

        self.private_directory = tempfile.TemporaryDirectory()

        self.override_settings = override_settings(
            SRI_PRIVATE_STORAGE_ROOT=self.private_directory.name
        )

        self.override_settings.enable()

        self.person = Person.objects.create(
            identification="1790000001001",
            person_type="LEGAL",
            full_name="Empresa Test",
        )

        self.company = Company.objects.create(
            person=self.person,
            commercial_name="SISADMI TEST",
        )

    def tearDown(self):

        self.override_settings.disable()
        self.private_directory.cleanup()

    def test_create_sri_certificate(self):

        certificate = SriCertificate.objects.create(
            company=self.company,
            secret_key="SISADMI_TEST_CERTIFICATE_PASSWORD",
        )

        self.assertEqual(
            certificate.company,
            self.company,
        )

        self.assertEqual(
            certificate.secret_key,
            "SISADMI_TEST_CERTIFICATE_PASSWORD",
        )

        self.assertTrue(
            certificate.is_active
        )

        self.assertFalse(
            certificate.is_default
        )

    def test_certificate_file_is_stored_in_private_storage(self):

        certificate = SriCertificate.objects.create(
            company=self.company,
            secret_key="SISADMI_TEST_CERTIFICATE_PASSWORD",
        )

        certificate.certificate_file.save(
            "certificate.p12",
            ContentFile(b"test-pkcs12"),
        )

        certificate.refresh_from_db()

        file_path = Path(
            certificate.certificate_file.path
        )

        private_root = Path(
            self.private_directory.name
        )

        self.assertTrue(
            file_path.exists()
        )

        self.assertTrue(
            file_path.is_relative_to(
                private_root
            )
        )

    def test_certificate_does_not_have_public_url(self):

        certificate = SriCertificate.objects.create(
            company=self.company,
            secret_key="SISADMI_TEST_CERTIFICATE_PASSWORD",
        )

        certificate.certificate_file.save(
            "certificate.p12",
            ContentFile(b"test-pkcs12"),
        )

        with self.assertRaisesMessage(
            ValueError,
            (
                "Los certificados SRI son archivos privados "
                "y no disponen de una URL pública."
            ),
        ):

            certificate.certificate_file.url

    def test_only_one_active_default_certificate_per_company(self):

        SriCertificate.objects.create(
            company=self.company,
            secret_key="SISADMI_CERTIFICATE_ONE",
            is_default=True,
        )

        with self.assertRaises(IntegrityError):

            SriCertificate.objects.create(
                company=self.company,
                secret_key="SISADMI_CERTIFICATE_TWO",
                is_default=True,
            )

    def test_inactive_default_certificate_does_not_block_new_default(self):

        SriCertificate.objects.create(
            company=self.company,
            secret_key="SISADMI_CERTIFICATE_OLD",
            is_default=True,
            is_active=False,
        )

        certificate = SriCertificate.objects.create(
            company=self.company,
            secret_key="SISADMI_CERTIFICATE_NEW",
            is_default=True,
            is_active=True,
        )

        self.assertTrue(
            certificate.is_default
        )

        self.assertTrue(
            certificate.is_active
        )
