from datetime import datetime, timezone
from unittest import TestCase

from django.db import connection
from django.test import TransactionTestCase

from core.constants.sri import SriEnvironment
from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus
from sri.constants.document_status import SriDocumentStatus
from sri.models import SriAuthorizationAttempt, SriAuthorizationMessage
from sri.services.electronic_document_authorization_service import (
    AuthorizationAlreadyInProgress,
    SriAuthorizationMessageData,
    SriAuthorizationProtocolError,
    SriAuthorizationResult,
    SriAuthorizationTransportError,
)
from sri.tests.authorization_domain_test_support import (
    create_authorized_document,
    create_received_document,
)
from sri.tests.authorization_soap_test_support import (
    FakeClientFactory,
    FakeSoapOperation,
    authorization,
    message,
    response,
)


AUTHORIZED_XML = "<authorized>integration</authorized>"


def entrypoint():
    from sri.services.electronic_document_authorization_entrypoint import (
        authorize_electronic_document,
    )
    return authorize_electronic_document


class FakeAdapter:
    def __init__(self, result=None, error=None, on_query=None):
        self.result = result
        self.error = error
        self.on_query = on_query
        self.call_count = 0
        self.access_keys = []
        self.environments = []

    def query_authorization(self, *, access_key, environment):
        self.call_count += 1
        self.access_keys.append(access_key)
        self.environments.append(environment)
        if self.on_query:
            self.on_query()
        if self.error:
            raise self.error
        return self.result


def authorized_result(document, xml=AUTHORIZED_XML):
    return SriAuthorizationResult(
        outcome=SriAuthorizationAttemptStatus.AUTHORIZED,
        access_key_consulted=document.access_key,
        authorization_number="AUTH-INTEGRATION-001",
        authorization_date=datetime(2026, 9, 27, 15, 30, tzinfo=timezone.utc),
        environment=document.environment,
        authorized_xml=xml,
        messages=(SriAuthorizationMessageData("INFO", "60", "ok", None),),
    )


class AuthorizationEntrypointREDTests(TransactionTestCase):
    def setUp(self):
        self.context, self.document = create_received_document()

    def invoke(self, adapter=None, client_factory=None):
        return entrypoint()(
            electronic_document=self.document,
            adapter=adapter,
            client_factory=client_factory,
        )

    def test_entrypoint_uses_explicit_adapter_and_persisted_authorities(self):
        adapter = FakeAdapter(result=authorized_result(self.document))
        result = self.invoke(adapter=adapter)
        self.assertIsInstance(result, type(self.document))
        self.assertEqual(adapter.call_count, 1)
        self.assertEqual(adapter.access_keys, [self.document.access_key])
        self.assertEqual(adapter.environments, [SriEnvironment.TEST])

    def test_production_environment_is_read_from_document(self):
        self.document.environment = SriEnvironment.PRODUCTION
        self.document.save(update_fields=["environment"])
        adapter = FakeAdapter(result=authorized_result(self.document))
        self.invoke(adapter=adapter)
        self.assertEqual(adapter.environments, [SriEnvironment.PRODUCTION])

    def test_authorized_result_is_finalized_through_c13a(self):
        original_xml = self.document.xml
        adapter = FakeAdapter(result=authorized_result(self.document))
        result = self.invoke(adapter=adapter)
        self.document.refresh_from_db()
        attempt = SriAuthorizationAttempt.objects.get(electronic_document=self.document)
        self.assertIs(result.__class__, self.document.__class__)
        self.assertEqual(self.document.status, SriDocumentStatus.AUTHORIZED)
        self.assertEqual(self.document.authorization_number, "AUTH-INTEGRATION-001")
        self.assertEqual(self.document.authorization_date, datetime(2026, 9, 27, 15, 30, tzinfo=timezone.utc))
        self.assertEqual(self.document.authorized_xml, AUTHORIZED_XML)
        self.assertEqual(self.document.xml, original_xml)
        self.assertEqual(attempt.status, SriAuthorizationAttemptStatus.AUTHORIZED)
        self.assertEqual(SriAuthorizationMessage.objects.filter(attempt=attempt).count(), 1)

    def test_not_authorized_is_finalized_as_rejected(self):
        adapter = FakeAdapter(result=SriAuthorizationResult(
            outcome=SriAuthorizationAttemptStatus.NOT_AUTHORIZED,
            access_key_consulted=self.document.access_key,
            environment=self.document.environment,
            messages=(SriAuthorizationMessageData("ERROR", "46", "No autorizado", None),),
        ))
        self.invoke(adapter=adapter)
        self.document.refresh_from_db()
        attempt = SriAuthorizationAttempt.objects.get(electronic_document=self.document)
        self.assertEqual(self.document.status, SriDocumentStatus.REJECTED)
        self.assertEqual(attempt.status, SriAuthorizationAttemptStatus.NOT_AUTHORIZED)
        self.assertIsNone(self.document.authorized_xml)

    def test_pending_keeps_document_received(self):
        adapter = FakeAdapter(result=SriAuthorizationResult(
            outcome=SriAuthorizationAttemptStatus.PENDING,
            access_key_consulted=self.document.access_key,
            environment=self.document.environment,
        ))
        self.invoke(adapter=adapter)
        self.document.refresh_from_db()
        attempt = SriAuthorizationAttempt.objects.get(electronic_document=self.document)
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)
        self.assertEqual(attempt.status, SriAuthorizationAttemptStatus.PENDING)
        self.assertIsNone(self.document.authorization_number)
        self.assertIsNone(self.document.authorization_date)
        self.assertIsNone(self.document.authorized_xml)

    def test_transport_error_propagates_and_marks_uncertain(self):
        adapter = FakeAdapter(error=SriAuthorizationTransportError("timeout"))
        with self.assertRaises(SriAuthorizationTransportError):
            self.invoke(adapter=adapter)
        attempt = SriAuthorizationAttempt.objects.get(electronic_document=self.document)
        self.document.refresh_from_db()
        self.assertEqual(attempt.status, SriAuthorizationAttemptStatus.UNCERTAIN)
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)

    def test_protocol_error_propagates_and_marks_protocol_error(self):
        adapter = FakeAdapter(error=SriAuthorizationProtocolError("malformed"))
        with self.assertRaises(SriAuthorizationProtocolError):
            self.invoke(adapter=adapter)
        attempt = SriAuthorizationAttempt.objects.get(electronic_document=self.document)
        self.document.refresh_from_db()
        self.assertEqual(attempt.status, SriAuthorizationAttemptStatus.PROTOCOL_ERROR)
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)

    def test_authorized_document_is_idempotent(self):
        document = self.document
        document.status = SriDocumentStatus.AUTHORIZED
        document.authorization_number = "AUTH-EXISTING"
        document.authorization_date = datetime(2026, 9, 27, 15, 30, tzinfo=timezone.utc)
        document.authorized_xml = "<existing-authorized/>"
        document.save(update_fields=["status", "authorization_number", "authorization_date", "authorized_xml"])
        adapter = FakeAdapter(result=authorized_result(document, "<unchanged/>") )
        before = {
            "xml": document.xml,
            "authorized_xml": document.authorized_xml,
            "authorization_number": document.authorization_number,
        }
        result = entrypoint()(electronic_document=document, adapter=adapter)
        document.refresh_from_db()
        self.assertEqual(adapter.call_count, 0)
        self.assertEqual(SriAuthorizationAttempt.objects.filter(electronic_document=document).count(), 0)
        self.assertEqual(result.status, SriDocumentStatus.AUTHORIZED)
        self.assertEqual(document.xml, before["xml"])
        self.assertEqual(document.authorized_xml, before["authorized_xml"])
        self.assertEqual(document.authorization_number, before["authorization_number"])

    def test_in_progress_is_rejected_before_adapter(self):
        attempt = SriAuthorizationAttempt.objects.create(
            electronic_document=self.document,
            status=SriAuthorizationAttemptStatus.IN_PROGRESS,
            access_key=self.document.access_key,
            environment=self.document.environment,
            started_at=datetime(2026, 9, 27, 15, 30, tzinfo=timezone.utc),
        )
        adapter = FakeAdapter(result=authorized_result(self.document))
        with self.assertRaises(AuthorizationAlreadyInProgress):
            self.invoke(adapter=adapter)
        self.assertEqual(adapter.call_count, 0)
        self.assertEqual(SriAuthorizationAttempt.objects.filter(electronic_document=self.document).count(), 1)

    def test_default_wiring_uses_same_client_factory_offline(self):
        factory = FakeClientFactory(
            operation=FakeSoapOperation(
                response=response(
                    key=self.document.access_key,
                    authorizations=[authorization(environment="PRUEBAS", comprobante=AUTHORIZED_XML)],
                )
            )
        )
        result = self.invoke(client_factory=factory)
        self.document.refresh_from_db()
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(factory.calls[0]["wsdl"], "https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl")
        self.assertEqual(factory.operation.call_count, 1)
        self.assertEqual(factory.operation.arguments, [self.document.access_key])
        self.assertEqual(result.status, SriDocumentStatus.AUTHORIZED)

    def test_explicit_adapter_wins_over_client_factory(self):
        class ExplodingFactory:
            call_count = 0
            def __call__(self, **kwargs):
                self.call_count += 1
                raise AssertionError("No debe construirse factory cuando hay adapter explícito.")

        adapter = FakeAdapter(result=authorized_result(self.document))
        factory = ExplodingFactory()
        self.invoke(adapter=adapter, client_factory=factory)
        self.assertEqual(adapter.call_count, 1)
        self.assertEqual(factory.call_count, 0)

    def test_authorization_makes_one_adapter_call(self):
        adapter = FakeAdapter(result=authorized_result(self.document))
        self.invoke(adapter=adapter)
        self.assertEqual(adapter.call_count, 1)



class AuthorizationEntrypointTransactionREDTests(TransactionTestCase):
    reset_sequences = True

    def test_external_call_is_outside_atomic_block(self):
        _, document = create_received_document()
        observed = []

        def observe():
            observed.append(connection.in_atomic_block)

        adapter = FakeAdapter(result=authorized_result(document), on_query=observe)
        entrypoint()(electronic_document=document, adapter=adapter)
        self.assertEqual(observed, [False])
