"""R-05 HTTP/crypto integration. SOAP responses are simulated, never real SRI evidence."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Sequence, SriConfiguration, Company, Branch
from inventory.models import Stock
from people.models import Person
from sales.models import Sale
from sales.constants.payment_method import PaymentMethod
from sri.models import ElectronicDocument, SriReceptionAttempt, SriAuthorizationAttempt, SriCertificate
from sri.services.electronic_document_signing_service import ElectronicDocumentSigningService
from sri.services.invoice_validation import verify_signed_invoice, FiscalValidationError
from sri.tests.electronic_document_signing_test_support import create_certificate_record
from sri.tests.helpers.invoice_factory import create_test_invoice_environment
from sri.tests.authorization_soap_test_support import authorization, response, message


class HumanInvoiceWorkflowTests(TestCase):
    def setUp(self):
        self.env = create_test_invoice_environment()
        self.company, self.branch = self.env['company'], self.env['branch']
        SriConfiguration.objects.create(company=self.company, environment='1')
        Sequence.objects.create(company=self.company, branch=self.branch,
            document_type=self.env['sale'].document_type, name='R05 sales', prefix='VEN-', series='001')
        Stock.objects.create(company=self.company, branch=self.branch, warehouse=self.env['warehouse'],
                             product=self.env['product'], quantity=Decimal('10'))
        self.certificate, self.password, self.public_certificate = create_certificate_record(self.company)
        self.user = get_user_model().objects.create_user('r05-operator')
        self.user.profile.companies.add(self.company)
        self.user.profile.branches.add(self.branch)
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='sri',
            codename__in=['view_electronicdocument', 'change_electronicdocument']))
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        session = self.client.session
        session.update({'company_id': self.company.pk, 'branch_id': self.branch.pk})
        session.save()
        self.network_guard = patch('requests.sessions.Session.request', side_effect=AssertionError('NO REAL SRI IN TEST'))
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)
        import os
        self.addCleanup(os.environ.pop, self.certificate.secret_key, None)

    def post(self, path, data=None):
        if 'csrftoken' not in self.client.cookies:
            self.client.get(reverse('sale_create'))
        return self.client.post(path, data or {}, HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def prepare(self):
        data = {'customer_id': self.env['customer'].pk, 'warehouse_id': self.env['warehouse'].pk,
            'issue_date': '2026-10-15', 'notes': 'R05 SIMULATED TEST', 'payment_method': PaymentMethod.CREDIT_CARD,
            'details-TOTAL_FORMS': '1', 'details-INITIAL_FORMS': '0', 'details-MIN_NUM_FORMS': '1',
            'details-MAX_NUM_FORMS': '1000', 'details-0-product_id': self.env['product'].pk,
            'details-0-quantity': '2', 'details-0-unit_price': '50', 'details-0-discount': '0'}
        self.assertEqual(self.post(reverse('sale_create'), data).status_code, 302)
        sale = Sale.objects.latest('pk')
        self.assertEqual(self.post(reverse('sale_confirm', args=[sale.pk])).status_code, 302)
        self.assertEqual(self.post(reverse('sale_prepare_fiscal', args=[sale.pk]),
            {'point_of_emission': self.env['emission_point'].pk}).status_code, 302)
        document = ElectronicDocument.objects.get(object_id=sale.pk)
        return sale, document

    def sign(self, document):
        result = self.post(reverse('electronic_document_sign', args=[document.pk]))
        self.assertContains(result, 'firmó correctamente')
        document.refresh_from_db()
        self.assertEqual(document.status, 'SIGNED')

    def reception_factory(self, state='RECIBIDA'):
        msg = SimpleNamespace(tipo='ERROR', identificador='35', mensaje='SIMULATED SRI MESSAGE', informacionAdicional='<script>unsafe</script>')
        answer = SimpleNamespace(estado=state, comprobantes=SimpleNamespace(comprobante=[SimpleNamespace(mensajes=SimpleNamespace(mensaje=[msg]))]))
        operation = Mock(return_value=answer)
        return SimpleNamespace(service=SimpleNamespace(validarComprobante=operation)), operation

    def test_full_human_workflow_with_simulated_soap_and_real_local_pkcs12_signature(self):
        sale, document = self.prepare()
        self.sign(document)
        signed = document.xml
        verify_signed_invoice(signed, certificate=self.public_certificate)
        client, operation = self.reception_factory()
        with patch('sri.clients.sri_reception_soap_adapter.SriReceptionSoapAdapter._create_client', return_value=client) as factory:
            page = self.post(reverse('electronic_document_receive', args=[document.pk]))
        self.assertContains(page, 'RECIBIDA')
        operation.assert_called_once_with(xml=signed.encode('utf-8'))
        self.assertIn('celcer.sri.gob.ec', factory.call_args.kwargs['wsdl'])
        document.refresh_from_db()
        self.assertEqual(document.status, 'RECEIVED')
        answer = response(key=document.access_key, authorizations=[authorization(number=document.access_key,
            date=datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc), environment='PRUEBAS', comprobante=signed,
            messages=(message(tipo='INFO', mensaje='SIMULATED AUTHORIZATION, NOT REAL SRI EVIDENCE'),))])
        query = Mock(return_value=answer)
        auth_client = SimpleNamespace(service=SimpleNamespace(autorizacionComprobante=query))
        with patch('sri.clients.sri_authorization_soap_adapter.SriAuthorizationSoapAdapter._create_client', return_value=auth_client) as factory:
            page = self.post(reverse('electronic_document_authorize', args=[document.pk]))
        self.assertContains(page, 'AUTORIZADO')
        self.assertContains(page, 'SIMULATED AUTHORIZATION, NOT REAL SRI EVIDENCE')
        query.assert_called_once_with(claveAccesoComprobante=document.access_key)
        document.refresh_from_db();sale.refresh_from_db()
        self.assertEqual(document.authorized_xml, signed)
        self.assertEqual(document.xml, signed)
        self.assertEqual(document.status, 'AUTHORIZED')
        self.assertEqual(sale.status, 'CONFIRMED')
        self.assertEqual(SriReceptionAttempt.objects.filter(electronic_document=document).count(), 1)
        self.assertEqual(SriAuthorizationAttempt.objects.filter(electronic_document=document).count(), 1)
        with patch('sri.clients.sri_authorization_soap_adapter.SriAuthorizationSoapAdapter._create_client') as duplicate:
            self.post(reverse('electronic_document_authorize', args=[document.pk]))
            duplicate.assert_not_called()
        self.assertEqual(SriAuthorizationAttempt.objects.filter(electronic_document=document).count(), 1)

    def test_invalid_xml_blocks_signing_before_pkcs12_resolution(self):
        _, document = self.prepare()
        bad = document.xml.replace('<importeTotal>115.00</importeTotal>', '<importeTotal>116.00</importeTotal>')
        document.xml = bad;document.save(update_fields=['xml'])
        with patch.object(ElectronicDocumentSigningService, '_resolve_signer') as resolve:
            page = self.post(reverse('electronic_document_sign', args=[document.pk]))
            resolve.assert_not_called()
        self.assertContains(page, 'XML fiscal inválido')
        document.refresh_from_db()
        self.assertEqual(document.status, 'GENERATED')
        self.assertEqual(document.xml, bad)
        self.assertFalse(SriReceptionAttempt.objects.exists())

    def test_unsigned_or_tampered_document_cannot_create_attempt_or_network_client(self):
        _, document = self.prepare()
        with patch('sri.clients.sri_reception_soap_adapter.SriReceptionSoapAdapter._create_client') as client:
            self.post(reverse('electronic_document_receive', args=[document.pk]))
            client.assert_not_called()
        self.sign(document)
        document.xml = document.xml.replace('Producto Test', 'TAMPERED PRODUCT')
        document.save(update_fields=['xml'])
        with patch('sri.clients.sri_reception_soap_adapter.SriReceptionSoapAdapter._create_client') as client:
            page = self.post(reverse('electronic_document_receive', args=[document.pk]))
            client.assert_not_called()
        self.assertContains(page, 'firma XAdES')
        self.assertFalse(SriReceptionAttempt.objects.exists())

    def test_signing_error_is_recorded_without_secrets_or_state_change(self):
        _, document = self.prepare();source = document.xml
        with patch('sri.services.pkcs12_xml_signer.Pkcs12XmlSigner.sign', side_effect=RuntimeError('PRIVATE-PASSWORD-SENTINEL')):
            page = self.post(reverse('electronic_document_sign', args=[document.pk]))
        self.assertNotContains(page, 'PRIVATE-PASSWORD-SENTINEL')
        document.refresh_from_db()
        self.assertEqual(document.status, 'GENERATED')
        self.assertEqual(document.xml, source)
        self.assertTrue(document.error_message)
        self.assertNotIn('PRIVATE-PASSWORD-SENTINEL', document.error_message)

    def test_permissions_and_csrf_block_mutation(self):
        _, document = self.prepare()
        url = reverse('electronic_document_sign', args=[document.pk])
        self.assertEqual(self.client.post(url).status_code, 403)
        change = Permission.objects.get(content_type__app_label='sri', codename='change_electronicdocument')
        self.user.user_permissions.remove(change)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.post(url).status_code, 403)
        document.refresh_from_db();self.assertEqual(document.status, 'GENERATED')

    def test_foreign_company_document_is_inaccessible(self):
        _, document = self.prepare()
        other = Company.objects.create(person=Person.objects.create(identification='R05-OTHER', full_name='PRIVATE OTHER'), commercial_name='Other')
        branch = Branch.objects.create(company=other, code='001', name='Other')
        ElectronicDocument.objects.filter(pk=document.pk).update(company=other, branch=branch)
        for name in ('electronic_document_sign', 'electronic_document_receive', 'electronic_document_authorize'):
            with self.subTest(route=name):
                self.assertEqual(self.post(reverse(name, args=[document.pk])).status_code, 404)

    def test_devuelta_is_displayed_distinctly_with_escaped_sri_messages(self):
        _, document = self.prepare();self.sign(document)
        client, _ = self.reception_factory('DEVUELTA')
        with patch('sri.clients.sri_reception_soap_adapter.SriReceptionSoapAdapter._create_client', return_value=client):
            page = self.post(reverse('electronic_document_receive', args=[document.pk]))
        self.assertContains(page, 'DEVUELTA');self.assertContains(page, 'SIMULATED SRI MESSAGE')
        self.assertNotContains(page, '<script>unsafe</script>')
        document.refresh_from_db();self.assertEqual(document.status, 'REJECTED')

    def received_for_authorization(self):
        _, document = self.prepare()
        self.sign(document)
        client, _ = self.reception_factory()
        with patch('sri.clients.sri_reception_soap_adapter.SriReceptionSoapAdapter._create_client', return_value=client):
            self.post(reverse('electronic_document_receive', args=[document.pk]))
        document.refresh_from_db()
        self.assertEqual(document.status, 'RECEIVED')
        return document

    def test_http_authorization_rejection_is_not_presented_as_success(self):
        document = self.received_for_authorization()
        answer = response(key=document.access_key, authorizations=[authorization(
            state='NO AUTORIZADO', number=None, date=None, comprobante=None,
            messages=(message(tipo='ERROR', identificador='R06', mensaje='SIMULATED FISCAL REJECTION'),),
        )])
        operation = Mock(return_value=answer)
        client = SimpleNamespace(service=SimpleNamespace(autorizacionComprobante=operation))
        with patch('sri.clients.sri_authorization_soap_adapter.SriAuthorizationSoapAdapter._create_client', return_value=client):
            page = self.post(reverse('electronic_document_authorize', args=[document.pk]))
        self.assertContains(page, 'NO AUTORIZADO')
        self.assertContains(page, 'SIMULATED FISCAL REJECTION')
        self.assertNotContains(page, 'Resultado: AUTORIZADO')
        document.refresh_from_db()
        self.assertEqual(document.status, 'REJECTED')
        self.assertFalse(document.authorization_number)
        self.assertFalse(document.authorized_xml)
        self.assertEqual(document.authorization_attempts.get().status, 'NOT_AUTHORIZED')
        operation.assert_called_once_with(claveAccesoComprobante=document.access_key)

    def test_http_authorization_transport_error_is_not_presented_as_success(self):
        from requests.exceptions import Timeout
        document = self.received_for_authorization()
        operation = Mock(side_effect=Timeout('PRIVATE-R06-TRANSPORT-SENTINEL'))
        client = SimpleNamespace(service=SimpleNamespace(autorizacionComprobante=operation))
        with patch('sri.clients.sri_authorization_soap_adapter.SriAuthorizationSoapAdapter._create_client', return_value=client):
            page = self.post(reverse('electronic_document_authorize', args=[document.pk]))
        self.assertContains(page, 'UNCERTAIN')
        self.assertNotContains(page, 'Resultado: AUTORIZADO')
        self.assertNotContains(page, 'PRIVATE-R06-TRANSPORT-SENTINEL')
        document.refresh_from_db()
        self.assertEqual(document.status, 'RECEIVED')
        self.assertFalse(document.authorization_number)
        self.assertFalse(document.authorized_xml)
        attempt = document.authorization_attempts.get()
        self.assertEqual(attempt.status, 'UNCERTAIN')
        self.assertNotIn('PRIVATE-R06-TRANSPORT-SENTINEL', attempt.error_message)
        operation.assert_called_once_with(claveAccesoComprobante=document.access_key)
