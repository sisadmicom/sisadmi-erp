from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from django.db import connection, connections
from django.test import TransactionTestCase

from sri.constants.document_status import SriDocumentStatus
from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus
from sri.models import SriAuthorizationAttempt
from sri.services.electronic_document_authorization_service import (
    AuthorizationAlreadyInProgress,
    ElectronicDocumentAuthorizationService,
)
from sri.tests.authorization_domain_test_support import (
    AUTHORIZED,
    AuthorizationResultData,
    FakeAuthorizationAdapter,
    create_received_document,
)


class ElectronicDocumentAuthorizationConcurrencyREDTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        self.context, self.document = create_received_document()
        self.adapter = FakeAuthorizationAdapter(
            result=AuthorizationResultData(
                outcome=AUTHORIZED,
                access_key_consulted=self.document.access_key,
                authorization_number="AUTH-001",
                authorization_date=__import__("datetime").datetime(2026, 9, 27, tzinfo=__import__("datetime").timezone.utc),
                environment=self.document.environment,
                authorized_xml="<authorized/>",
            )
        )
        self.barrier = Barrier(2)
        self.transport_started = Event()
        self.release_transport = Event()

    def test_second_worker_cannot_create_second_active_attempt(self):
        def receive(*, access_key, environment):
            self.adapter.calls.append((access_key, environment))
            self.transport_started.set()
            self.release_transport.wait(timeout=10)
            return self.adapter.result

        self.adapter.query_authorization = receive

        def worker():
            connections.close_all()
            try:
                self.barrier.wait(timeout=10)
                result = ElectronicDocumentAuthorizationService.authorize(
                    electronic_document=self.document,
                    adapter=self.adapter,
                )
                return ("success", result.status)
            except (AuthorizationAlreadyInProgress, ValueError) as error:
                return ("rejected", type(error).__name__)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            self.assertTrue(self.transport_started.wait(timeout=10))
            self.release_transport.set()
            results = [future.result(timeout=20) for future in futures]

        self.document.refresh_from_db()
        self.assertEqual([item[0] for item in results].count("success"), 1)
        self.assertEqual([item[0] for item in results].count("rejected"), 1)
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual(SriAuthorizationAttempt.objects.filter(electronic_document=self.document).count(), 1)
        self.assertEqual(self.document.status, SriDocumentStatus.AUTHORIZED)
        self.assertEqual(SriAuthorizationAttempt.objects.filter(electronic_document=self.document, status=SriAuthorizationAttemptStatus.AUTHORIZED).count(), 1)
