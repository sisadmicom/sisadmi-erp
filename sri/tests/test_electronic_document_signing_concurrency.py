from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connection, connections
from django.test import TransactionTestCase

from sri.constants.document_status import SriDocumentStatus
from sri.tests.electronic_document_signing_test_support import (
    create_certificate_record,
    create_generated_document,
)


class ElectronicDocumentSigningConcurrencyREDTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        self.context, self.electronic = create_generated_document()
        self.certificate, self.password, self.x509_certificate = create_certificate_record(
            self.context["company"],
        )

    def test_concurrent_signing_executes_single_effective_signature(self):
        barrier = Barrier(2)
        calls = []

        def worker():
            connections.close_all()
            try:
                from sri.services.electronic_document_signing_service import (
                    ElectronicDocumentSigningService,
                )

                barrier.wait(timeout=10)
                result = ElectronicDocumentSigningService.sign(
                    electronic_document=self.electronic,
                )
                calls.append("signed")
                return ("success", result.status)
            except Exception as error:
                calls.append("rejected")
                return ("rejected", type(error).__name__, str(error))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))

        self.electronic.refresh_from_db()
        self.assertEqual([result[0] for result in results].count("success"), 1)
        self.assertEqual([result[0] for result in results].count("rejected"), 1)
        self.assertEqual(self.electronic.status, SriDocumentStatus.SIGNED)
        self.assertEqual(calls.count("signed"), 1)
