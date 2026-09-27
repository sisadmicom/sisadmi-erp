from datetime import timedelta
from unittest import TestCase

from django.test import TestCase as DjangoTestCase
from django.test import TransactionTestCase
from django.utils import timezone

from sri.constants.document_status import SriDocumentStatus
from sri.tests.reception_test_support import (
    AmbiguousReceptionError,
    FakeReceptionAdapter,
    IN_PROGRESS,
    REJECTED,
    RECEIVED,
    ReceptionMessageData,
    ReceptionResult,
    UNCERTAIN,
    create_signed_document,
    fiscal_snapshot,
    another_db_attempt_count,
    reception_models,
)


class ElectronicDocumentReceptionServiceREDTests(DjangoTestCase):
    def setUp(self):
        self.context, self.document = create_signed_document()
        self.adapter = FakeReceptionAdapter(
            result=ReceptionResult(outcome=RECEIVED)
        )
        self.before = fiscal_snapshot(self.document)

    def _boundary(self):
        try:
            from sri.services.electronic_document_reception_service import (
                ElectronicDocumentReceptionService,
            )
        except (ImportError, ModuleNotFoundError) as error:
            raise AssertionError(
                "C-12A ElectronicDocumentReceptionService is not implemented."
            ) from error
        return ElectronicDocumentReceptionService

    def _submit(self):
        return self._boundary().submit(
            electronic_document=self.document,
            adapter=self.adapter,
        )

    def _assert_identity(self):
        self.document.refresh_from_db()
        after = fiscal_snapshot(self.document)
        self.assertEqual(after, self.before)

    def test_signed_document_received_by_sri_becomes_received(self):
        result = self._submit()
        Attempt, _ = reception_models()
        self.document.refresh_from_db()
        attempt = Attempt.objects.get(electronic_document=self.document)
        self.assertEqual(result.pk, self.document.pk)
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)
        self.assertEqual(attempt.status, RECEIVED)
        self.assertIsNotNone(attempt.completed_at)
        self.assertEqual(len(self.adapter.calls), 1)
        self._assert_identity()
        self.assertIsNone(self.document.authorization_number)
        self.assertIsNone(self.document.authorization_date)

    def test_submit_uses_exact_persisted_signed_xml_and_environment(self):
        self._submit()
        self.assertEqual(
            self.adapter.calls,
            [(self.before["xml"], self.before["environment"])],
        )
        self._assert_identity()

    def test_wrong_document_status_is_rejected_without_transport(self):
        for status in (
            SriDocumentStatus.GENERATED,
            SriDocumentStatus.RECEIVED,
            SriDocumentStatus.REJECTED,
        ):
            with self.subTest(status=status):
                self.document.status = status
                self.document.save(update_fields=["status"])
                with self.assertRaises(ValueError):
                    self._submit()
                self.assertEqual(len(self.adapter.calls), 0)
                self.document.refresh_from_db()
                self.assertEqual(self.document.status, status)

    def test_returned_response_rejects_document_and_persists_all_messages(self):
        messages = (
            ReceptionMessageData("ERROR", "001", "Primer mensaje", "Detalle A"),
            ReceptionMessageData("ERROR", "002", "Segundo mensaje", "Detalle B"),
        )
        self.adapter.result = ReceptionResult(
            outcome=REJECTED,
            messages=messages,
        )
        self._submit()
        Attempt, Message = reception_models()
        self.document.refresh_from_db()
        attempt = Attempt.objects.get(electronic_document=self.document)
        persisted = Message.objects.filter(attempt=attempt)
        self.assertEqual(self.document.status, SriDocumentStatus.REJECTED)
        self.assertEqual(attempt.status, REJECTED)
        self.assertIsNotNone(attempt.completed_at)
        self.assertEqual(persisted.count(), 2)
        self.assertEqual(
            set(persisted.values_list("identifier", "message", "additional_information")),
            {("001", "Primer mensaje", "Detalle A"), ("002", "Segundo mensaje", "Detalle B")},
        )
        self.assertEqual(self.document.error_message, self.before.get("error_message"))
        self._assert_identity()

    def test_transport_timeout_creates_uncertain_attempt_without_false_document_state(self):
        self.adapter.error = AmbiguousReceptionError("response lost")
        with self.assertRaises(AmbiguousReceptionError):
            self._submit()
        Attempt, _ = reception_models()
        self.document.refresh_from_db()
        attempt = Attempt.objects.get(electronic_document=self.document)
        self.assertEqual(attempt.status, UNCERTAIN)
        self.assertIsNotNone(attempt.completed_at)
        self.assertEqual(self.document.status, SriDocumentStatus.SIGNED)
        self.assertNotEqual(attempt.error_message, "")
        self.assertEqual(len(self.adapter.calls), 1)
        self._assert_identity()

    def test_active_attempt_blocks_duplicate_submission(self):
        Attempt, _ = reception_models()
        Attempt.objects.create(
            electronic_document=self.document,
            status=IN_PROGRESS,
            attempted_at=timezone.now(),
        )
        with self.assertRaises(ValueError):
            self._submit()
        self.assertEqual(len(self.adapter.calls), 0)
        self.assertEqual(Attempt.objects.filter(electronic_document=self.document).count(), 1)

    def test_uncertain_attempt_blocks_duplicate_submission(self):
        Attempt, _ = reception_models()
        Attempt.objects.create(
            electronic_document=self.document,
            status=UNCERTAIN,
            attempted_at=timezone.now() - timedelta(minutes=1),
            completed_at=timezone.now(),
            error_type="timeout",
            error_message="response lost",
        )
        with self.assertRaises(ValueError):
            self._submit()
        self.assertEqual(len(self.adapter.calls), 0)
        self.assertEqual(Attempt.objects.filter(electronic_document=self.document).count(), 1)

    def test_reception_preserves_fiscal_identity(self):
        self._submit()
        self._assert_identity()

    def test_reception_does_not_request_authorization(self):
        self._submit()
        self.document.refresh_from_db()
        self.assertIsNone(self.document.authorization_number)
        self.assertIsNone(self.document.authorization_date)

    def test_unknown_reception_response_never_creates_false_received_state(self):
        self.adapter.result = ReceptionResult(outcome="UNKNOWN_EXTERNAL_STATE")
        self._submit()
        Attempt, _ = reception_models()
        self.document.refresh_from_db()
        attempt = Attempt.objects.get(electronic_document=self.document)
        self.assertNotEqual(self.document.status, SriDocumentStatus.RECEIVED)
        self.assertNotEqual(self.document.status, SriDocumentStatus.REJECTED)
        self.assertEqual(attempt.status, UNCERTAIN)

    def test_invalid_environment_creates_no_attempt(self):
        Attempt, _ = reception_models()
        self.document.environment = "X"
        self.document.save(update_fields=["environment"])
        with self.assertRaises(ValueError):
            self._submit()
        self.assertEqual(len(self.adapter.calls), 0)
        self.assertEqual(Attempt.objects.filter(electronic_document=self.document).count(), 0)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, SriDocumentStatus.SIGNED)

    def test_preflight_failure_creates_no_attempt(self):
        Attempt, _ = reception_models()
        self.document.xml = ""
        self.document.save(update_fields=["xml"])
        with self.assertRaises(ValueError):
            self._submit()
        self.assertEqual(len(self.adapter.calls), 0)
        self.assertEqual(Attempt.objects.filter(electronic_document=self.document).count(), 0)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, SriDocumentStatus.SIGNED)


class ElectronicDocumentReceptionCommitTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.context, self.document = create_signed_document()
        self.adapter = FakeReceptionAdapter(
            result=ReceptionResult(outcome=RECEIVED)
        )

    def _boundary(self):
        from sri.services.electronic_document_reception_service import (
            ElectronicDocumentReceptionService,
        )
        return ElectronicDocumentReceptionService

    def _submit(self):
        return self._boundary().submit(
            electronic_document=self.document,
            adapter=self.adapter,
        )

    def test_claim_is_committed_before_transport(self):
        observed = []
        self.adapter.on_receive = lambda: observed.append(
            another_db_attempt_count(self.document.pk)
        )
        self._submit()
        self.assertEqual(observed, [1])



class ReceptionAttemptModelIntegrityREDTests(DjangoTestCase):
    def test_database_rejects_second_active_reception_attempt(self):
        from django.db import IntegrityError, transaction

        Attempt, _ = reception_models()
        _, document = create_signed_document()
        now = timezone.now()
        Attempt.objects.create(
            electronic_document=document,
            status=IN_PROGRESS,
            attempted_at=now,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Attempt.objects.create(
                    electronic_document=document,
                    status=UNCERTAIN,
                    attempted_at=now,
                )
        self.assertEqual(Attempt.objects.filter(electronic_document=document).count(), 1)
