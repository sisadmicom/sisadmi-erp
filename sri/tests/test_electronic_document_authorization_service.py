from datetime import datetime, timezone
from unittest import TestCase

from django.db import IntegrityError, transaction
from django.test import TestCase as DjangoTestCase
from django.test import TransactionTestCase

from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus
from sri.constants.document_status import SriDocumentStatus
from sri.models import SriAuthorizationAttempt, SriAuthorizationMessage
from sri.services.electronic_document_authorization_service import (
    AuthorizationAlreadyInProgress,
    ElectronicDocumentAuthorizationService,
    SriAuthorizationMessageData,
    SriAuthorizationProtocolError,
    SriAuthorizationResult,
    SriAuthorizationTransportError,
)
from sri.tests.authorization_domain_test_support import (
    AUTHORIZED,
    IN_PROGRESS,
    NOT_AUTHORIZED,
    PENDING,
    PROTOCOL_ERROR,
    AuthorizationMessageData,
    AuthorizationResultData,
    FakeAuthorizationAdapter,
    create_received_document,
    fiscal_snapshot,
)


class AuthorizationServiceREDTests(DjangoTestCase):
    def setUp(self):
        self.context, self.document = create_received_document()
        self.adapter = FakeAuthorizationAdapter(
            result=AuthorizationResultData(
                outcome=AUTHORIZED,
                access_key_consulted=self.document.access_key,
                authorization_number="AUTH-001",
                authorization_date=datetime(2026, 9, 27, 15, 30, tzinfo=timezone.utc),
                environment=self.document.environment,
                authorized_xml="<authorized/>",
            )
        )

    def submit(self):
        return ElectronicDocumentAuthorizationService.authorize(
            electronic_document=self.document,
            adapter=self.adapter,
        )

    def attempts(self):
        return SriAuthorizationAttempt.objects.filter(electronic_document=self.document)

    def test_only_received_document_can_start_authorization(self):
        for status in (
            SriDocumentStatus.DRAFT,
            SriDocumentStatus.PENDING,
            SriDocumentStatus.GENERATED,
            SriDocumentStatus.SIGNED,
            SriDocumentStatus.SENT,
            SriDocumentStatus.REJECTED,
            SriDocumentStatus.ERROR,
        ):
            with self.subTest(status=status):
                self.document.status = status
                self.document.save(update_fields=["status"])
                with self.assertRaises(ValueError):
                    self.submit()
                self.assertEqual(len(self.adapter.calls), 0)
                self.assertEqual(self.attempts().count(), 0)
                self.document.status = SriDocumentStatus.RECEIVED
                self.document.save(update_fields=["status"])

    def test_persisted_access_key_is_sent_to_adapter(self):
        self.submit()
        self.assertEqual(self.adapter.calls[0][0], self.document.access_key)

    def test_persisted_environment_is_sent_to_adapter(self):
        self.submit()
        self.assertEqual(self.adapter.calls[0][1], self.document.environment)

    def test_in_progress_attempt_exists_before_adapter_call(self):
        observed = []

        def observe():
            attempt = self.attempts().get()
            observed.append((attempt.status, attempt.access_key, attempt.environment, attempt.started_at))

        self.adapter.on_query = observe
        self.submit()
        self.assertEqual(observed[0][0], IN_PROGRESS)
        self.assertEqual(observed[0][1], self.document.access_key)
        self.assertEqual(observed[0][2], self.document.environment)
        self.assertIsNotNone(observed[0][3])

    def test_authorized_result_finalizes_document_with_official_evidence(self):
        result = self.submit()
        self.document.refresh_from_db()
        attempt = self.attempts().get()
        self.assertEqual(result.status, SriDocumentStatus.AUTHORIZED)
        self.assertEqual(self.document.status, SriDocumentStatus.AUTHORIZED)
        self.assertEqual(self.document.authorization_number, "AUTH-001")
        self.assertEqual(self.document.authorization_date, datetime(2026, 9, 27, 15, 30, tzinfo=timezone.utc))
        self.assertEqual(self.document.authorized_xml, "<authorized/>")
        self.assertEqual(attempt.status, AUTHORIZED)
        self.assertIsNotNone(attempt.finished_at)

    def test_authorized_result_does_not_modify_original_signed_xml(self):
        original = self.document.xml
        self.submit()
        self.document.refresh_from_db()
        self.assertEqual(self.document.xml, original)
        self.assertNotEqual(self.document.authorized_xml, original)

    def test_not_authorized_finalizes_document_as_rejected(self):
        self.adapter.result = AuthorizationResultData(
            outcome=NOT_AUTHORIZED,
            access_key_consulted=self.document.access_key,
            environment=self.document.environment,
            messages=(AuthorizationMessageData("ERROR", "46", "RUC no existe", None),),
        )
        self.submit()
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, SriDocumentStatus.REJECTED)
        self.assertEqual(self.attempts().get().status, NOT_AUTHORIZED)
        self.assertEqual(len(self.adapter.calls), 1)

    def test_pending_result_keeps_document_received(self):
        self.adapter.result = AuthorizationResultData(
            outcome=PENDING,
            access_key_consulted=self.document.access_key,
            environment=self.document.environment,
        )
        self.submit()
        self.document.refresh_from_db()
        attempt = self.attempts().get()
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)
        self.assertEqual(attempt.status, PENDING)
        self.assertIsNone(self.document.authorization_number)
        self.assertIsNone(self.document.authorization_date)
        self.assertIsNone(self.document.authorized_xml)
        self.assertIsNotNone(attempt.finished_at)

    def test_pending_result_from_adapter_follows_pending_policy(self):
        self.adapter.result = AuthorizationResultData(PENDING, self.document.access_key)
        self.submit()
        self.assertEqual(self.attempts().get().status, PENDING)

    def test_all_authorization_messages_are_persisted(self):
        messages = tuple(
            AuthorizationMessageData("ERROR", str(i), f"m{i}", f"a{i}")
            for i in range(3)
        )
        self.adapter.result = AuthorizationResultData(
            NOT_AUTHORIZED, self.document.access_key, environment=self.document.environment, messages=messages
        )
        self.submit()
        self.assertEqual(SriAuthorizationMessage.objects.filter(attempt=self.attempts().get()).count(), 3)

    def test_repeated_identical_messages_are_preserved(self):
        message = AuthorizationMessageData("ERROR", "70", "procesando", None)
        self.adapter.result = AuthorizationResultData(
            NOT_AUTHORIZED, self.document.access_key, environment=self.document.environment, messages=(message, message)
        )
        self.submit()
        self.assertEqual(SriAuthorizationMessage.objects.filter(attempt=self.attempts().get()).count(), 2)

    def test_transport_error_marks_attempt_uncertain_and_keeps_document_received(self):
        self.adapter.error = SriAuthorizationTransportError("timeout")
        with self.assertRaises(SriAuthorizationTransportError):
            self.submit()
        self.document.refresh_from_db()
        attempt = self.attempts().get()
        self.assertEqual(attempt.status, SriAuthorizationAttemptStatus.UNCERTAIN)
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)
        self.assertIsNone(self.document.authorization_number)

    def test_protocol_error_marks_attempt_protocol_error_and_keeps_document_received(self):
        self.adapter.error = SriAuthorizationProtocolError("bad response")
        with self.assertRaises(SriAuthorizationProtocolError):
            self.submit()
        self.document.refresh_from_db()
        self.assertEqual(self.attempts().get().status, PROTOCOL_ERROR)
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)

    def test_result_access_key_mismatch_cannot_finalize_document(self):
        self.adapter.result = AuthorizationResultData(AUTHORIZED, "different", "AUTH-001", datetime.now(timezone.utc), self.document.environment, "<authorized/>")
        with self.assertRaises(SriAuthorizationProtocolError):
            self.submit()
        self.document.refresh_from_db()
        self.assertEqual(self.attempts().get().status, PROTOCOL_ERROR)
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)
        self.assertIsNone(self.document.authorization_number)

    def test_result_environment_mismatch_cannot_finalize_document(self):
        self.adapter.result = AuthorizationResultData(AUTHORIZED, self.document.access_key, "AUTH-001", datetime.now(timezone.utc), "2", "<authorized/>")
        with self.assertRaises(SriAuthorizationProtocolError):
            self.submit()
        self.assertEqual(self.attempts().get().status, PROTOCOL_ERROR)

    def test_authorized_result_requires_authorization_number(self):
        self.adapter.result = AuthorizationResultData(AUTHORIZED, self.document.access_key, environment=self.document.environment, authorization_date=datetime.now(timezone.utc), authorized_xml="<authorized/>")
        with self.assertRaises(SriAuthorizationProtocolError):
            self.submit()
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)

    def test_authorized_result_requires_official_authorization_date(self):
        self.adapter.result = AuthorizationResultData(AUTHORIZED, self.document.access_key, authorization_number="AUTH-001", environment=self.document.environment, authorized_xml="<authorized/>")
        with self.assertRaises(SriAuthorizationProtocolError):
            self.submit()

    def test_authorized_result_requires_timezone_aware_date(self):
        self.adapter.result = AuthorizationResultData(AUTHORIZED, self.document.access_key, "AUTH-001", datetime(2026, 9, 27, 15, 30), self.document.environment, "<authorized/>")
        with self.assertRaises(SriAuthorizationProtocolError):
            self.submit()

    def test_authorized_result_requires_returned_xml(self):
        self.adapter.result = AuthorizationResultData(AUTHORIZED, self.document.access_key, "AUTH-001", datetime.now(timezone.utc), self.document.environment, None)
        with self.assertRaises(SriAuthorizationProtocolError):
            self.submit()

    def test_authorization_date_is_the_official_returned_date(self):
        official = datetime(2024, 1, 2, 3, 4, tzinfo=timezone.utc)
        self.adapter.result = AuthorizationResultData(AUTHORIZED, self.document.access_key, "AUTH-001", official, self.document.environment, "<authorized/>")
        self.submit()
        self.document.refresh_from_db()
        self.assertEqual(self.document.authorization_date, official)

    def test_authorized_document_does_not_call_adapter_or_create_attempt(self):
        self.document.status = SriDocumentStatus.AUTHORIZED
        self.document.authorization_number = self.document.access_key
        self.document.authorization_date = datetime(2026, 9, 27, 15, 30, tzinfo=timezone.utc)
        self.document.authorized_xml = "<authorized/>"
        self.document.save(update_fields=["status", "authorization_number", "authorization_date", "authorized_xml"])
        before = fiscal_snapshot(self.document)
        adapter = FakeAuthorizationAdapter()
        result = ElectronicDocumentAuthorizationService.authorize(electronic_document=self.document, adapter=adapter)
        self.document.refresh_from_db()
        self.assertEqual(adapter.calls, [])
        self.assertEqual(SriAuthorizationAttempt.objects.filter(electronic_document=self.document).count(), 0)
        self.assertEqual(fiscal_snapshot(self.document), before)
        self.assertEqual(result.pk, self.document.pk)

    def test_authorization_service_does_not_call_reception_service(self):
        self.submit()
        self.assertEqual(len(self.adapter.calls), 1)

    def test_authorization_does_not_regenerate_access_key_or_signed_xml(self):
        before = fiscal_snapshot(self.document)
        self.submit()
        self.assertEqual(self.document.__class__.objects.get(pk=self.document.pk).access_key, before["access_key"])
        self.assertEqual(self.document.__class__.objects.get(pk=self.document.pk).xml, before["xml"])

    def test_authorized_xml_is_stored_separately_from_original_xml(self):
        original = self.document.xml
        self.submit()
        self.document.refresh_from_db()
        self.assertEqual(self.document.xml, original)
        self.assertEqual(self.document.authorized_xml, "<authorized/>")

    def test_unexpected_adapter_exception_marks_uncertain_and_reraises(self):
        self.adapter.error = RuntimeError("unexpected")
        with self.assertRaises(RuntimeError):
            self.submit()
        self.document.refresh_from_db()
        self.assertEqual(self.attempts().get().status, SriAuthorizationAttemptStatus.UNCERTAIN)
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)

    def test_missing_access_key_fails_before_attempt_and_adapter(self):
        self.document.access_key = None
        self.document.save(update_fields=["access_key"])
        with self.assertRaises(ValueError):
            self.submit()
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(self.attempts().count(), 0)

    def test_invalid_environment_fails_before_attempt_and_adapter(self):
        self.document.environment = "X"
        self.document.save(update_fields=["environment"])
        with self.assertRaises(ValueError):
            self.submit()
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(self.attempts().count(), 0)

    def test_pending_performs_only_one_adapter_call(self):
        self.adapter.result = AuthorizationResultData(PENDING, self.document.access_key)
        self.submit()
        self.assertEqual(len(self.adapter.calls), 1)

    def test_not_authorized_performs_only_one_adapter_call(self):
        self.adapter.result = AuthorizationResultData(NOT_AUTHORIZED, self.document.access_key, environment=self.document.environment)
        self.submit()
        self.assertEqual(len(self.adapter.calls), 1)

    def test_transport_error_performs_only_one_adapter_call(self):
        self.adapter.error = SriAuthorizationTransportError("timeout")
        with self.assertRaises(SriAuthorizationTransportError):
            self.submit()
        self.assertEqual(len(self.adapter.calls), 1)

    def test_database_prevents_two_in_progress_attempts_for_same_document(self):
        now = datetime.now(timezone.utc)
        SriAuthorizationAttempt.objects.create(electronic_document=self.document, status=IN_PROGRESS, access_key=self.document.access_key, environment=self.document.environment, started_at=now)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SriAuthorizationAttempt.objects.create(electronic_document=self.document, status=IN_PROGRESS, access_key=self.document.access_key, environment=self.document.environment, started_at=now)


class AuthorizationAtomicBoundaryTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.context, self.document = create_received_document()
        self.adapter = FakeAuthorizationAdapter(
            result=AuthorizationResultData(
                outcome=AUTHORIZED,
                access_key_consulted=self.document.access_key,
                authorization_number="AUTH-001",
                authorization_date=datetime(2026, 9, 27, 15, 30, tzinfo=timezone.utc),
                environment=self.document.environment,
                authorized_xml="<authorized/>",
            )
        )

    def test_adapter_call_occurs_outside_atomic_block(self):
        observed = []
        from django.db import connection
        self.adapter.on_query = lambda: observed.append(connection.in_atomic_block)
        ElectronicDocumentAuthorizationService.authorize(
            electronic_document=self.document,
            adapter=self.adapter,
        )
        self.assertEqual(observed, [False])
