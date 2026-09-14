from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connection, connections
from django.test import TransactionTestCase

from core.models import DocumentType, PointOfEmission
from sales.models import Sale
from sri.models import ElectronicDocument, FiscalSequence
from sri.services.electronic_document_service import ElectronicDocumentService
from sri.tests.helpers.invoice_factory import create_test_invoice_environment


class FiscalSequenceConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        DocumentType.objects.get_or_create(
            code=Sale.DOCUMENT_TYPE_CODE, defaults={'name': 'Venta', 'category': 'SALES'},
        )
        self.context = create_test_invoice_environment()
        self.sale = self.context['sale']
        self.point = self.context['emission_point']

    def second_sale(self):
        return Sale.objects.create(
            company=self.sale.company, branch=self.sale.branch,
            warehouse=self.sale.warehouse, customer=self.sale.customer,
            document_type=self.sale.document_type, status=self.sale.status,
            issue_date=self.sale.issue_date, number='ERP/ALFA',
        )

    def run_race(self, origins, points):
        origin_barrier = Barrier(2)
        counter_barrier = Barrier(2)

        def worker(args):
            sale_id, point_id = args
            connections.close_all()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '8s'")
                    cursor.execute("SET statement_timeout = '12s'")
                    cursor.execute('SELECT pg_backend_pid()')
                    pid = cursor.fetchone()[0]
                sale = Sale.objects.get(pk=sale_id)
                point = PointOfEmission.objects.get(pk=point_id)
                reached_origin = False
                reached_counter = False

                def coordinate(execute, sql, params, many, context):
                    nonlocal reached_origin, reached_counter
                    result = execute(sql, params, many, context)
                    # Both real existence reads finish before either proceeds.
                    # Never wait at a barrier while holding a shared row lock.
                    if sql.startswith('SELECT') and 'FROM "sri_electronicdocument"' in sql and not reached_origin:
                        reached_origin = True
                        origin_barrier.wait(timeout=10)
                    if (sql.startswith('SELECT') and 'FROM "sri_fiscalsequence"' in sql
                            and 'FOR UPDATE' not in sql and not reached_counter):
                        reached_counter = True
                        counter_barrier.wait(timeout=10)
                    return result

                with connection.execute_wrapper(coordinate):
                    try:
                        electronic = ElectronicDocumentService.create(
                            document=sale, document_type='01', emission_point=point,
                            environment='1', emission_type='1',
                        )
                        outcome = ('created', electronic.pk, electronic.sequential)
                    except ValueError as error:
                        outcome = ('rejected', str(error))
                return pid, outcome, reached_origin, reached_counter
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, pair) for pair in zip(origins, points)]
            results = [future.result(timeout=25) for future in futures]
        self.assertEqual(len({result[0] for result in results}), 2)
        self.assertTrue(all(result[2] and result[3] for result in results))
        return [result[1] for result in results]

    def assert_two_documents(self):
        other = self.second_sale()
        outcomes = self.run_race([self.sale.pk, other.pk], [self.point.pk] * 2)
        self.assertEqual([outcome[0] for outcome in outcomes], ['created', 'created'])
        self.assertEqual({outcome[2] for outcome in outcomes}, {'000000001', '000000002'})
        self.assertEqual(ElectronicDocument.objects.count(), 2)
        self.assertEqual(FiscalSequence.objects.count(), 1)
        self.assertEqual(FiscalSequence.objects.get().next_number, 3)

    def test_first_counter_creation_for_distinct_documents(self):
        self.assert_two_documents()

    def test_existing_counter_for_distinct_documents(self):
        FiscalSequence.objects.create(company=self.sale.company, establishment='001',
                                      emission_point='001', document_type='01')
        self.assert_two_documents()

    def assert_same_origin(self, points):
        outcomes = self.run_race([self.sale.pk] * 2, points)
        self.assertCountEqual([outcome[0] for outcome in outcomes], ['created', 'rejected'])
        rejected = next(outcome for outcome in outcomes if outcome[0] == 'rejected')
        self.assertEqual(rejected[1], 'El documento ya tiene un documento electrónico generado.')
        self.assertEqual(ElectronicDocument.objects.count(), 1)
        self.assertEqual(FiscalSequence.objects.count(), 1)
        electronic = ElectronicDocument.objects.get()
        counter = FiscalSequence.objects.get()
        self.assertEqual(electronic.sequential, '000000001')
        self.assertEqual(counter.next_number, 2)
        self.assertEqual(counter.emission_point, electronic.emission_point)

    def test_same_origin_same_scope_rolls_back_losing_reservation(self):
        self.assert_same_origin([self.point.pk] * 2)

    def test_same_origin_different_points_removes_losing_counter(self):
        other_point = PointOfEmission.objects.create(
            branch=self.sale.branch, code='002', name='Otra caja',
        )
        self.assert_same_origin([self.point.pk, other_point.pk])
