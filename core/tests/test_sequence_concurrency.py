from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connection, connections
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from core.constants.document_type_codes import DocumentTypeCodes
from core.models import Branch, Company, Sequence
from core.models.document_type import DocumentType
from core.services.sequence_service import SequenceService
from people.models import Person


class SequenceConcurrencyTest(TransactionTestCase):
    def test_concurrent_requests_lock_and_increment_the_same_sequence(self):
        document_type, _ = DocumentType.objects.get_or_create(
            code=DocumentTypeCodes.SALES_INVOICE,
            defaults={"name": "Ventas", "category": "SALES"},
        )
        person = Person.objects.create(
            identification="1790000001001", person_type="LEGAL", full_name="Empresa",
        )
        company = Company.objects.create(person=person)
        branch = Branch.objects.create(company=company, code="001", name="Matriz")
        sequence = Sequence.objects.create(
            company=company, branch=branch, document_type=document_type,
            code="CUSTOM", name="Concurrente", prefix="ERP-", next_number=25,
        )
        barrier = Barrier(4)

        def consume():
            try:
                barrier.wait(timeout=10)
                return [SequenceService.next_number(company, branch, document_type) for _ in range(5)]
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: consume(), range(4)))
        self.assertEqual(
            sorted(number for numbers in results for number in numbers),
            [f"ERP-001-{number:06d}" for number in range(25, 45)],
        )
        sequence.refresh_from_db()
        self.assertEqual(sequence.next_number, 45)
        with CaptureQueriesContext(connection) as queries:
            SequenceService.next_number(company, branch, document_type)
        self.assertTrue(any("FOR UPDATE" in query["sql"] for query in queries))
