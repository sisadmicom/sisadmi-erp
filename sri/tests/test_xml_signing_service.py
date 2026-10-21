import os
from unittest.mock import Mock

from django.test import TestCase

from sri.services.invoice_validation import FiscalValidationError, SIGNING_ERROR, company_signer, verify_signed_invoice
from sri.services.xml_signing_service import XmlSigningService
from sri.tests.electronic_document_signing_test_support import create_generated_document, create_certificate_record


class XmlSigningServiceTest(TestCase):
    def setUp(self):
        context, self.document = create_generated_document()
        self.record, _, self.public_certificate = create_certificate_record(context['company'])
        self.addCleanup(os.environ.pop, self.record.secret_key, None)
        self.signer = company_signer(context['company'])

    def test_sign_generated_document(self):
        source = self.document.xml
        result = XmlSigningService.sign(self.document, self.signer)
        result.refresh_from_db()
        self.assertEqual(result.status, 'SIGNED')
        verify_signed_invoice(result.xml, certificate=self.public_certificate, source_xml=source)

    def test_rejects_document_without_xml(self):
        self.document.xml = None;self.document.save(update_fields=['xml'])
        with self.assertRaisesMessage(ValueError, 'no tiene XML'):
            XmlSigningService.sign(self.document, self.signer)

    def test_rejects_non_generated_document(self):
        self.document.status = 'DRAFT';self.document.save(update_fields=['status'])
        with self.assertRaisesMessage(ValueError, 'Solo se pueden firmar'):
            XmlSigningService.sign(self.document, self.signer)

    def test_keeps_generated_and_records_safe_error_when_signer_fails(self):
        signer = Mock();signer.sign.side_effect = RuntimeError('PRIVATE SECRET SENTINEL')
        source = self.document.xml
        with self.assertRaises(FiscalValidationError):
            XmlSigningService.sign(self.document, signer, certificate=self.public_certificate)
        signer.sign.assert_called_once_with(source)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, 'GENERATED')
        self.assertEqual(self.document.xml, source)
        self.assertEqual(self.document.error_message, SIGNING_ERROR)
        self.assertNotIn('PRIVATE SECRET SENTINEL', self.document.error_message)
