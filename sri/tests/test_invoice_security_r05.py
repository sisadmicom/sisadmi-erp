from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from sri.tests.r05_support import signed_invoice_fixture, valid_invoice_xml


class InvoiceSecurityOfflineTests(SimpleTestCase):
    def test_signed_fiscal_invoice_verifies_without_modifying_bytes(self):
        from sri.services.invoice_validation import verify_signed_invoice
        source, signed, certificate = signed_invoice_fixture()
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No SRI network")):
            self.assertIsNone(verify_signed_invoice(signed, certificate=certificate.certificate, source_xml=source))
        self.assertEqual(signed, signed_invoice_fixture()[1])

    def test_invalid_xml_and_unsigned_xml_cannot_reach_reception_client(self):
        from sri.clients.sri_reception_soap_adapter import SriReceptionSoapAdapter
        source, signed, _ = signed_invoice_fixture()
        for xml in ("<factura/>", source, signed.replace("TEST PRODUCT", "TAMPERED")):
            factory = Mock()
            with self.subTest(xml_kind=xml[:20]), self.assertRaises(ValueError):
                SriReceptionSoapAdapter(client_factory=factory).receive(xml=xml, environment="1")
            factory.assert_not_called()

    def test_valid_signed_xml_cannot_be_signed_over_a_different_source(self):
        from sri.services.invoice_validation import verify_signed_invoice
        source, signed, certificate = signed_invoice_fixture()
        with self.assertRaises(ValueError):
            verify_signed_invoice(signed, certificate=certificate.certificate,
                                  source_xml=source.replace("TEST PRODUCT", "DIFFERENT PRODUCT"))

    def test_signature_from_another_certificate_is_rejected(self):
        from sri.services.invoice_validation import verify_signed_invoice
        from sri.tests.electronic_document_signing_test_support import build_runtime_certificate
        from sri.services.certificate_service import CertificateService
        _, signed, _ = signed_invoice_fixture()
        raw, password, _ = build_runtime_certificate(common_name="OTHER UNIT TEST CERTIFICATE")
        other = CertificateService.load(raw, password)
        with self.assertRaises(ValueError):
            verify_signed_invoice(signed, certificate=other.certificate)

    def test_production_is_blocked_before_any_soap_client_is_created(self):
        from sri.clients.sri_reception_soap_adapter import SriReceptionSoapAdapter
        from sri.clients.sri_authorization_soap_adapter import SriAuthorizationSoapAdapter
        _, signed, _ = signed_invoice_fixture()
        for adapter, method, args in ((SriReceptionSoapAdapter, "receive", {"xml": signed}),
                (SriAuthorizationSoapAdapter, "query_authorization", {"access_key": "1" * 49})):
            factory = Mock()
            with self.subTest(adapter=adapter.__name__), self.assertRaises(ValueError):
                getattr(adapter(client_factory=factory), method)(environment="2", **args)
            factory.assert_not_called()

    def test_real_client_rejects_wrong_wsdl_tls_and_soap_binding(self):
        from types import SimpleNamespace
        from sri.clients import sri_reception_soap_adapter as reception
        from sri.clients import sri_authorization_soap_adapter as authorization
        for module, adapter, wsdl in (
            (reception, reception.SriReceptionSoapAdapter, reception.TEST_RECEPTION_WSDL),
            (authorization, authorization.SriAuthorizationSoapAdapter, authorization.TEST_AUTHORIZATION_WSDL),
        ):
            with self.subTest(adapter=adapter.__name__):
                with patch.object(module, "Client") as client:
                    for uri, verify in (("https://cel.sri.gob.ec/forbidden", True), (wsdl, False)):
                        with self.assertRaises(ValueError):
                            adapter._create_client(wsdl=uri, verify=verify, connect_timeout=10, operation_timeout=60)
                    client.assert_not_called()
                with patch.object(module, "Client", return_value=SimpleNamespace(service=SimpleNamespace(
                        _binding_options={"address": "https://cel.sri.gob.ec/forbidden"}))), \
                        patch.object(module, "Transport"), patch.object(module.requests, "Session") as session:
                    with self.assertRaises(ValueError):
                        adapter._create_client(wsdl=wsdl, verify=True, connect_timeout=10, operation_timeout=60)
                    self.assertEqual(session.return_value.max_redirects, 0)

    def test_legacy_submission_cannot_bypass_fiscal_validation(self):
        from types import SimpleNamespace
        from sri.services.sri_submission_service import SriSubmissionService
        client = Mock()
        document = SimpleNamespace(status='SIGNED', xml='<factura/>', environment='1')
        with self.assertRaises(ValueError):
            SriSubmissionService.submit(document, client)
        client.send.assert_not_called()

    def test_authorized_evidence_must_be_the_matching_verified_signed_invoice(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from sri.services.electronic_document_authorization_service import (
            ElectronicDocumentAuthorizationService, SriAuthorizationResult, SriAuthorizationProtocolError,
        )
        from sri.services.invoice_validation import fiscal_root
        _, signed, _ = signed_invoice_fixture()
        key = fiscal_root(signed).findtext('infoTributaria/claveAcceso')
        document = SimpleNamespace(xml=signed, access_key=key, environment='1')
        good = SriAuthorizationResult('AUTHORIZED', key, key, datetime.now(timezone.utc), '1', signed, ())
        ElectronicDocumentAuthorizationService._validate_result(document, good)
        bad = SriAuthorizationResult('AUTHORIZED', key, key, datetime.now(timezone.utc), '1', '<authorized/>', ())
        with self.assertRaises(SriAuthorizationProtocolError):
            ElectronicDocumentAuthorizationService._validate_result(document, bad)

    def test_certificate_storage_is_private_and_external(self):
        import os, stat, tempfile
        from pathlib import Path
        from django.core.files.base import ContentFile
        from sri.storage import SriCertificateStorage
        with tempfile.TemporaryDirectory(prefix='sisadmi-r05-storage-') as directory:
            with self.settings(SRI_PRIVATE_STORAGE_ROOT=directory):
                storage = SriCertificateStorage()
                name = storage.save('issuer/test.p12', ContentFile(b'UNIT TEST STORAGE, NOT A REAL CERTIFICATE'))
                self.assertEqual(stat.S_IMODE(os.stat(storage.path(name)).st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(os.stat(Path(storage.path(name)).parent).st_mode), 0o700)
                with self.assertRaises(ValueError):
                    storage.url(name)
