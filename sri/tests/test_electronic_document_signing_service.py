import os
from datetime import datetime, timedelta
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from django.test import TestCase
from lxml import etree
from signxml import SignatureConfiguration, XMLVerifier

from core.models import Company
from people.models import Person
from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument
from sri.services.certificate_service import CertificateService
from sri.tests.electronic_document_signing_test_support import (
    assert_certificate_self_check,
    create_certificate_record,
    create_generated_document,
)


class ElectronicDocumentSigningBoundaryREDTests(TestCase):
    def setUp(self):
        self.context, self.electronic = create_generated_document()
        self.company = self.context["company"]
        self.original_xml = self.electronic.xml
        self.certificate, self.password, self.x509_certificate = create_certificate_record(
            self.company,
        )
        assert_certificate_self_check(
            self.certificate,
            self.password,
        )
        self.addCleanup(self._clear_test_secrets)

    def _clear_test_secrets(self):
        for key in list(os.environ):
            if key.startswith("C11_SECRET_"):
                os.environ.pop(key, None)

    def _boundary(self):
        from sri.services.electronic_document_signing_service import (
            ElectronicDocumentSigningService,
        )

        return ElectronicDocumentSigningService

    def _sign(self):
        return self._boundary().sign(electronic_document=self.electronic)

    def test_generated_document_is_signed_with_company_certificate(self):
        result = self._sign()

        self.assertEqual(result.pk, self.electronic.pk)
        self.assertEqual(result.status, SriDocumentStatus.SIGNED)
        self.assertNotEqual(result.xml, self.original_xml)
        self.assertIn("QualifyingProperties", result.xml)
        self.assertEqual(result.access_key, self.electronic.access_key)
        self.assertEqual(result.sequential, self.electronic.sequential)
        self.assertEqual(result.company_id, self.electronic.company_id)
        self.assertEqual(result.branch_id, self.electronic.branch_id)
        self.assertEqual(ElectronicDocument.objects.count(), 1)

    def test_sign_uses_persisted_electronic_document_xml(self):
        captured = []
        from sri.services.pkcs12_xml_signer import Pkcs12XmlSigner

        real_sign = Pkcs12XmlSigner.sign

        def capture(signer, xml):
            captured.append(xml)
            return real_sign(signer, xml)

        with patch.object(Pkcs12XmlSigner, "sign", capture):
            self._sign()

        self.assertEqual(captured, [self.original_xml])

    def test_signed_document_cannot_be_signed_again(self):
        self.electronic.status = SriDocumentStatus.SIGNED
        self.electronic.save(update_fields=["status"])
        snapshot = self.electronic.__class__.objects.get(pk=self.electronic.pk)

        service = self._boundary()
        with self.assertRaises(ValueError):
            service.sign(electronic_document=self.electronic)

        current = ElectronicDocument.objects.get(pk=self.electronic.pk)
        self.assertEqual(current.status, snapshot.status)
        self.assertEqual(current.xml, snapshot.xml)
        self.assertEqual(current.access_key, snapshot.access_key)
        self.assertEqual(current.sequential, snapshot.sequential)

    def test_missing_company_certificate_leaves_document_generated(self):
        self.certificate.delete()
        snapshot = ElectronicDocument.objects.get(pk=self.electronic.pk)

        with self.assertRaises(ValueError):
            self._sign()

        current = ElectronicDocument.objects.get(pk=self.electronic.pk)
        self.assertEqual(current.status, SriDocumentStatus.GENERATED)
        self.assertEqual(current.xml, snapshot.xml)
        self.assertEqual(current.error_message, snapshot.error_message)

    def test_expired_certificate_is_rejected_without_mutation(self):
        self.certificate.delete()
        self.certificate, _, _ = create_certificate_record(
            self.company,
            not_before=datetime.utcnow() - timedelta(days=3),
            not_after=datetime.utcnow() - timedelta(days=1),
        )
        snapshot = ElectronicDocument.objects.get(pk=self.electronic.pk)

        with self.assertRaises(ValueError):
            self._sign()

        current = ElectronicDocument.objects.get(pk=self.electronic.pk)
        self.assertEqual(current.status, SriDocumentStatus.GENERATED)
        self.assertEqual(current.xml, snapshot.xml)
        self.assertEqual(current.error_message, snapshot.error_message)

    def test_not_yet_valid_certificate_is_rejected_without_mutation(self):
        self.certificate.delete()
        self.certificate, _, _ = create_certificate_record(
            self.company,
            not_before=datetime.utcnow() + timedelta(days=1),
            not_after=datetime.utcnow() + timedelta(days=3),
        )
        snapshot = ElectronicDocument.objects.get(pk=self.electronic.pk)

        with self.assertRaises(ValueError):
            self._sign()

        current = ElectronicDocument.objects.get(pk=self.electronic.pk)
        self.assertEqual(current.status, SriDocumentStatus.GENERATED)
        self.assertEqual(current.xml, snapshot.xml)
        self.assertEqual(current.error_message, snapshot.error_message)

    def test_document_cannot_use_certificate_from_another_company(self):
        self.certificate.delete()
        other_person = Person.objects.create(
            identification="1790000002001",
            person_type="LEGAL",
            full_name="Otra Empresa",
        )
        other_company = Company.objects.create(
            person=other_person,
            commercial_name="Otra Empresa",
        )
        other_certificate, _, _ = create_certificate_record(other_company)
        snapshot = ElectronicDocument.objects.get(pk=self.electronic.pk)

        with self.assertRaises(ValueError):
            self._sign()

        self.assertTrue(other_certificate.is_active)
        current = ElectronicDocument.objects.get(pk=self.electronic.pk)
        self.assertEqual(current.status, SriDocumentStatus.GENERATED)
        self.assertEqual(current.xml, snapshot.xml)

    def test_signed_xml_is_cryptographically_verifiable(self):
        result = self._sign()
        certificate_pem = self.x509_certificate.public_bytes(serialization.Encoding.PEM)

        verified = XMLVerifier().verify(
            result.xml.encode("utf-8"),
            x509_cert=certificate_pem,
            expect_config=SignatureConfiguration(expect_references=3),
        )

        self.assertEqual(len(verified), 3)
        self.assertEqual(etree.fromstring(result.xml.encode("utf-8")).tag, "factura")

    def test_signing_failure_rolls_back_document_snapshot(self):
        snapshot = {
            field: getattr(self.electronic, field)
            for field in (
                "status", "xml", "error_message", "access_key", "sequential",
                "environment", "emission_type", "establishment", "emission_point",
            )
        }
        from sri.services.pkcs12_xml_signer import Pkcs12XmlSigner

        with patch.object(Pkcs12XmlSigner, "sign", side_effect=RuntimeError("c11 signing failure")):
            with self.assertRaises(RuntimeError):
                self._sign()

        current = ElectronicDocument.objects.get(pk=self.electronic.pk)
        for field, value in snapshot.items():
            self.assertEqual(getattr(current, field), value)

    def test_signing_does_not_change_fiscal_identity(self):
        before = {
            field: getattr(self.electronic, field)
            for field in (
                "pk", "company_id", "branch_id", "document_type", "environment",
                "emission_type", "establishment", "emission_point", "sequential",
                "numeric_code", "access_key", "object_id", "content_type_id",
            )
        }
        before_count = ElectronicDocument.objects.count()
        self._sign()
        current = ElectronicDocument.objects.get(pk=self.electronic.pk)

        for field, value in before.items():
            self.assertEqual(getattr(current, field), value)
        self.assertEqual(ElectronicDocument.objects.count(), before_count)
