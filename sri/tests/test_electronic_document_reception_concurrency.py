from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from django.db import connection, connections
from django.test import TransactionTestCase

from sri.constants.document_status import SriDocumentStatus
from sri.tests.reception_test_support import (
    FakeReceptionAdapter,
    RECEIVED,
    ReceptionResult,
    create_signed_document,
    reception_models,
)


class ElectronicDocumentReceptionConcurrencyREDTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        self.context, self.document = create_signed_document()
        self.adapter = FakeReceptionAdapter(
            result=ReceptionResult(outcome=RECEIVED),
        )
        self.barrier = Barrier(2)
        self.transport_started = Event()
        self.release_transport = Event()

    def test_concurrent_submission_claims_and_sends_once(self):
        def receive(*, xml, environment):
            with self.adapter._lock:
                self.adapter.calls.append((xml, environment))
            self.transport_started.set()
            self.release_transport.wait(timeout=10)
            return ReceptionResult(outcome=RECEIVED)

        self.adapter.receive = receive

        try:
            from sri.services.electronic_document_reception_service import (
                ElectronicDocumentReceptionService,
            )
        except (ImportError, ModuleNotFoundError) as error:
            raise AssertionError(
                "C-12A ElectronicDocumentReceptionService is not implemented."
            ) from error

        def worker():
            connections.close_all()
            try:
                self.barrier.wait(timeout=10)
                result = ElectronicDocumentReceptionService.submit(
                    electronic_document=self.document,
                    adapter=self.adapter,
                )
                return ("success", result.status)
            except (ValueError, RuntimeError, AssertionError, ImportError) as error:
                return ("rejected", type(error).__name__, str(error))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            self.assertTrue(self.transport_started.wait(timeout=10))
            self.release_transport.set()
            results = [future.result(timeout=20) for future in futures]

        Attempt, _ = reception_models()
        self.document.refresh_from_db()
        self.assertEqual([item[0] for item in results].count("success"), 1)
        self.assertEqual([item[0] for item in results].count("rejected"), 1)
        self.assertEqual(self.adapter.calls.__len__(), 1)
        self.assertEqual(Attempt.objects.filter(electronic_document=self.document).count(), 1)
        self.assertEqual(self.document.status, SriDocumentStatus.RECEIVED)
