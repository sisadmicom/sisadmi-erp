from unittest.mock import patch

from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase

from core.models import Company, Sequence
from people.models import Person
from sri.models import ElectronicDocument, FiscalSequence
from sri.services.fiscal_sequence_service import FiscalSequenceService
from sri.services.electronic_document_service import ElectronicDocumentService
from sri.tests.helpers.invoice_factory import create_test_invoice_environment


class FiscalSequenceServiceTests(TestCase):
    def setUp(self):
        self.context = create_test_invoice_environment()
        self.scope = dict(company=self.context['company'], establishment='001',
                          emission_point='001', document_type='01')

    def reserve(self, **overrides):
        return FiscalSequenceService.next_number(**(self.scope | overrides))

    def test_same_scope_and_timestamps(self):
        self.assertEqual(self.reserve(), '000000001')
        first_update = FiscalSequence.objects.get().updated_at
        self.assertEqual(self.reserve(), '000000002')
        counter = FiscalSequence.objects.get()
        self.assertEqual(counter.next_number, 3)
        self.assertGreaterEqual(counter.updated_at, first_update)

    def test_all_scope_dimensions_are_independent(self):
        company = Company.objects.create(person=Person.objects.create(
            identification='1790000002001', full_name='Otra empresa',
        ))
        self.assertEqual(self.reserve(), '000000001')
        for override in ({'company': company}, {'establishment': '002'},
                         {'emission_point': '002'}, {'document_type': '04'}):
            with self.subTest(override=override):
                self.assertEqual(self.reserve(**override), '000000001')
        self.assertEqual(FiscalSequence.objects.count(), 5)
        self.assertEqual(self.reserve(), '000000002')

    def test_invalid_codes_rejected_by_service_and_database(self):
        for field, valid in [('establishment', '001'), ('emission_point', '001'),
                             ('document_type', '01')]:
            for value in ['A' * len(valid), ' ' * len(valid), valid[:-1],
                          valid + '1', valid[:-1] + '\n', valid + '\n',
                          '１' * len(valid)]:
                with self.subTest(field=field, value=repr(value)):
                    with self.assertRaises(ValueError):
                        self.reserve(**{field: value})
                    with self.assertRaises(DatabaseError), transaction.atomic():
                        FiscalSequence.objects.create(**(self.scope | {field: value}))
        self.assertFalse(FiscalSequence.objects.exists())

    def test_database_range_and_unique_scope(self):
        for value in (0, 1000000001):
            with self.subTest(value=value):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    FiscalSequence.objects.create(**self.scope, next_number=value)
        FiscalSequence.objects.create(**self.scope)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FiscalSequence.objects.create(**self.scope)

    def test_exhaustion_does_not_wrap(self):
        counter = FiscalSequence.objects.create(**self.scope, next_number=999999999)
        self.assertEqual(self.reserve(), '999999999')
        counter.refresh_from_db()
        self.assertEqual(counter.next_number, 1000000000)
        with self.assertRaisesMessage(ValueError, 'agotada'):
            self.reserve()
        counter.refresh_from_db()
        self.assertEqual(counter.next_number, 1000000000)


class FiscalEmissionRollbackTests(TestCase):
    def setUp(self):
        self.context = create_test_invoice_environment()
        self.sale = self.context['sale']
        self.erp_sequence = Sequence.objects.create(
            company=self.sale.company, branch=self.sale.branch,
            document_type=self.sale.document_type, name='ERP', prefix='SAL-', next_number=26,
        )

    def issue(self):
        return ElectronicDocumentService.create(
            document=self.sale, document_type='01',
            emission_point=self.context['emission_point'],
            environment='1', emission_type='1',
        )

    def assert_erp_unchanged(self):
        self.erp_sequence.refresh_from_db()
        self.sale.refresh_from_db()
        self.assertEqual(self.erp_sequence.next_number, 26)
        self.assertEqual(self.sale.number, 'SAL-001-000000025')
        self.assertFalse(ElectronicDocument.objects.exists())

    def test_key_failure_rolls_back_existing_counter(self):
        counter = FiscalSequence.objects.create(
            company=self.sale.company, establishment='001', emission_point='001',
            document_type='01', next_number=17,
        )
        with patch('sri.services.access_key_service.AccessKeyService.generate',
                   side_effect=ValueError('fallo de clave')):
            with self.assertRaisesMessage(ValueError, 'fallo de clave'):
                self.issue()
        counter.refresh_from_db()
        self.assertEqual(counter.next_number, 17)
        self.assert_erp_unchanged()

    def test_key_failure_rolls_back_first_counter(self):
        with patch('sri.services.access_key_service.AccessKeyService.generate',
                   side_effect=ValueError('fallo de clave')):
            with self.assertRaises(ValueError):
                self.issue()
        self.assertFalse(FiscalSequence.objects.exists())
        self.assert_erp_unchanged()

    def test_real_insert_failure_is_not_translated_and_rolls_back(self):
        # Null origin ID fails on INSERT; no mock of DB/sequence/insert.
        self.sale.pk = None
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.issue()
        self.assertFalse(FiscalSequence.objects.exists())
        self.sale = self.context['sale'].__class__.objects.get()
        self.assert_erp_unchanged()

    def test_outer_failure_reverts_successful_emission(self):
        with self.assertRaisesMessage(ValueError, 'posterior'):
            with transaction.atomic():
                self.issue()
                raise ValueError('posterior')
        self.assertFalse(FiscalSequence.objects.exists())
        self.assert_erp_unchanged()

    def test_repeat_rejected_without_consumption(self):
        self.issue()
        with self.assertRaisesMessage(ValueError, 'ya tiene un documento electrónico'):
            self.issue()
        self.assertEqual(ElectronicDocument.objects.count(), 1)
        self.assertEqual(FiscalSequence.objects.get().next_number, 2)
