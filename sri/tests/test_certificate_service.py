from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from django.test import SimpleTestCase

from sri.services.certificate_service import (
    CertificateService,
)


class CertificateServiceTest(SimpleTestCase):

    PASSWORD = "test-password"

    @classmethod
    def setUpClass(cls):

        super().setUpClass()

        # ----------------------------------------------
        # 1. Generar clave privada de prueba
        # ----------------------------------------------

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # ----------------------------------------------
        # 2. Crear Subject
        # ----------------------------------------------

        subject = issuer = x509.Name(
            [
                x509.NameAttribute(
                    NameOID.COUNTRY_NAME,
                    "EC",
                ),
                x509.NameAttribute(
                    NameOID.ORGANIZATION_NAME,
                    "Sisadmi Test",
                ),
                x509.NameAttribute(
                    NameOID.COMMON_NAME,
                    "certificado.sisadmi.test",
                ),
            ]
        )

        # ----------------------------------------------
        # 3. Crear certificado
        # ----------------------------------------------

        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(
                private_key.public_key()
            )
            .serial_number(
                x509.random_serial_number()
            )
            .not_valid_before(
                datetime.utcnow()
            )
            .not_valid_after(
                datetime.utcnow()
                + timedelta(days=365)
            )
            .add_extension(
                x509.BasicConstraints(
                    ca=True,
                    path_length=None,
                ),
                critical=True,
            )
            .sign(
                private_key,
                hashes.SHA256(),
            )
        )

        # ----------------------------------------------
        # 4. Crear PKCS#12
        # ----------------------------------------------

        cls.p12_data = (
            pkcs12.serialize_key_and_certificates(
                name=b"sisadmi-test",
                key=private_key,
                cert=certificate,
                cas=None,
                encryption_algorithm=(
                    serialization.BestAvailableEncryption(
                        cls.PASSWORD.encode("utf-8")
                    )
                ),
            )
        )

        cls.certificate = certificate

    def test_load_certificate(self):

        result = CertificateService.load(
            certificate_data=self.p12_data,
            password=self.PASSWORD,
        )

        self.assertIsNotNone(
            result.private_key
        )

        self.assertIsNotNone(
            result.certificate
        )

    def test_load_certificate_has_private_key(self):

        result = CertificateService.load(
            certificate_data=self.p12_data,
            password=self.PASSWORD,
        )

        self.assertIsNotNone(
            result.private_key
        )

    def test_load_certificate_has_certificate(self):

        result = CertificateService.load(
            certificate_data=self.p12_data,
            password=self.PASSWORD,
        )

        self.assertEqual(
            result.certificate.serial_number,
            self.certificate.serial_number,
        )

    def test_rejects_empty_certificate(self):

        with self.assertRaisesMessage(
            ValueError,
            "El contenido del certificado no puede estar vacío.",
        ):

            CertificateService.load(
                certificate_data=b"",
                password=self.PASSWORD,
            )

    def test_rejects_missing_password(self):

        with self.assertRaisesMessage(
            ValueError,
            "La contraseña del certificado es obligatoria.",
        ):

            CertificateService.load(
                certificate_data=self.p12_data,
                password=None,
            )

    def test_rejects_invalid_password(self):

        with self.assertRaisesMessage(
            ValueError,
            "No se pudo cargar el certificado PKCS#12.",
        ):

            CertificateService.load(
                certificate_data=self.p12_data,
                password="wrong-password",
            )

    def test_get_certificate_serial_number(self):

        result = CertificateService.load(
            certificate_data=self.p12_data,
            password=self.PASSWORD,
        )

        serial = (
            CertificateService
            .get_certificate_serial_number(
                result.certificate
            )
        )

        self.assertEqual(
            serial,
            self.certificate.serial_number,
        )

    def test_get_certificate_pem(self):

        result = CertificateService.load(
            certificate_data=self.p12_data,
            password=self.PASSWORD,
        )

        pem = (
            CertificateService
            .get_certificate_pem(
                result.certificate
            )
        )

        self.assertTrue(
            pem.startswith(
                b"-----BEGIN CERTIFICATE-----"
            )
        )

    def test_get_certificate_not_valid_before(self):

        result = CertificateService.load(
            certificate_data=self.p12_data,
            password=self.PASSWORD,
        )

        not_valid_before = (
            CertificateService
            .get_certificate_not_valid_before(
                result.certificate
            )
        )

        self.assertIsNotNone(
            not_valid_before
        )


    def test_get_certificate_not_valid_after(self):

        result = CertificateService.load(
            certificate_data=self.p12_data,
            password=self.PASSWORD,
        )

        not_valid_after = (
            CertificateService
            .get_certificate_not_valid_after(
                result.certificate
            )
        )

        self.assertIsNotNone(
            not_valid_after
        )


    def test_certificate_is_valid(self):

        result = CertificateService.load(
            certificate_data=self.p12_data,
            password=self.PASSWORD,
        )

        self.assertTrue(
            CertificateService.is_certificate_valid(
                result.certificate
            )
        )


    def test_validate_certificate(self):

        result = CertificateService.load(
            certificate_data=self.p12_data,
            password=self.PASSWORD,
        )

        self.assertTrue(
            CertificateService.validate_certificate(
                result.certificate
            )
        )