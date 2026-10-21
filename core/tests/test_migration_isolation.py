"""Contratos del harness con transiciones PostgreSQL reales y sin datos DEV."""
import unittest
from types import SimpleNamespace

from django.db import connection, transaction
from django.db.migrations import Migration
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase

from core.testing.migration_isolation import (
    CUSTOMER, SUPPLIER, CATEGORY, CATEGORY_ASSIGNMENT, MigrationIsolationError, customer_migration_state,
    require_test_connection, schema_snapshot, validate_plan, applied_targets, supplier_migration_state,
)
from core.testing.runner import MigrationIsolationRunner, MigrationIsolatedSuite


class MigrationIsolationTests(TransactionTestCase):
    def setUp(self):
        require_test_connection(connection)
        self.initial = self.applied()
        self.targets = applied_targets(MigrationExecutor(connection), self.initial)
        self.assertIn(SUPPLIER, self.initial)
        self.schema = schema_snapshot(connection)
        # Registrar antes de cualquier transición. Nunca se borran fixtures
        # para eludir una guardia: los casos que fallan no clasifican Supplier.
        self.addCleanup(self.restore_schema)

    def applied(self):
        return set(MigrationExecutor(connection).loader.applied_migrations)

    def restore_schema(self):
        require_test_connection(connection)
        MigrationExecutor(connection).migrate(self.targets)
        self.assertEqual(self.applied(), self.initial)
        self.assertEqual(schema_snapshot(connection), self.schema)

    def test_complete_initial_state_and_exact_restoration(self):
        with customer_migration_state(connection):
            self.assertEqual(self.applied(), self.initial - {SUPPLIER, CATEGORY, CATEGORY_ASSIGNMENT})
            with connection.cursor() as cursor:
                columns = connection.introspection.get_table_description(cursor, 'people_supplier')
            self.assertNotIn('company_id', {column.name for column in columns})
        self.assertEqual(self.applied(), self.initial)
        self.assertEqual(schema_snapshot(connection), self.schema)

    def test_partial_initial_state_does_not_apply_pending_leaf(self):
        MigrationExecutor(connection).migrate([CUSTOMER])
        partial = self.applied()
        schema = schema_snapshot(connection)
        with customer_migration_state(connection):
            self.assertEqual(self.applied(), partial)
        self.assertEqual(self.applied(), partial)
        self.assertEqual(schema_snapshot(connection), schema)

    def test_preparation_failure_preserves_real_guard_and_classification(self):
        from core.models import Company
        from people.models import Person, Supplier
        person = Person.objects.create(identification='isolation', person_type='LEGAL', full_name='Isolation')
        company = Company.objects.create(person=person)
        supplier = Supplier.objects.create(person=person, company=company)
        with self.assertRaises(IrreversibleError):
            with customer_migration_state(connection):
                self.fail('No debe ejecutar el bloque si falla la preparación.')
        supplier.refresh_from_db()
        self.assertEqual(supplier.company_id, company.pk)
        self.assertEqual(self.applied(), self.initial)
        self.assertEqual(schema_snapshot(connection), self.schema)

    def test_body_failure_restores_then_propagates(self):
        with self.assertRaisesRegex(ValueError, 'fallo del cuerpo'):
            with customer_migration_state(connection):
                raise ValueError('fallo del cuerpo')
        self.assertEqual(self.applied(), self.initial)

    def test_restoration_failure_is_visible_and_not_claimed_successful(self):
        scope = customer_migration_state(connection)
        scope.__enter__()
        with transaction.atomic():
            with self.assertRaisesRegex(MigrationIsolationError, 'transacciones activas'):
                scope.__exit__(None, None, None)
        # El fallo real deja 0006 pendiente; cleanup registrado restaura después.
        self.assertNotIn(SUPPLIER, self.applied())

    def test_body_and_restoration_failures_are_both_propagated(self):
        scope = customer_migration_state(connection)
        scope.__enter__()
        failure = ValueError('cuerpo')
        with transaction.atomic():
            with self.assertRaises(BaseExceptionGroup) as caught:
                scope.__exit__(ValueError, failure, None)
        self.assertIs(caught.exception.exceptions[0], failure)
        self.assertIsInstance(caught.exception.exceptions[1], MigrationIsolationError)
        self.assertNotIn(SUPPLIER, self.applied())

    def test_active_transaction_rejected_before_schema_changes(self):
        with transaction.atomic():
            with self.assertRaisesRegex(MigrationIsolationError, 'transacciones activas'):
                with customer_migration_state(connection):
                    self.fail('No debe entrar dentro de una transacción.')
        self.assertEqual(self.applied(), self.initial)

    def test_category_data_blocks_reversal_without_deleting_records(self):
        from core.models import Company
        from people.models import Person, CustomerCategory
        company = Company.objects.create(person=Person.objects.create(
            identification="ui01-isolation", full_name="Isolation"))
        category = CustomerCategory.objects.create(company=company, code="KEEP", name="Conservar")
        for scope in (customer_migration_state, supplier_migration_state):
            with self.subTest(scope=scope.__name__):
                with self.assertRaisesRegex(MigrationIsolationError, "Categorías existentes"):
                    with scope(connection):
                        self.fail("No debe revertir una tabla con datos.")
        category.refresh_from_db()
        self.assertEqual(category.name, "Conservar")
        self.assertEqual(self.applied(), self.initial)
        self.assertEqual(schema_snapshot(connection), self.schema)

    def test_supplier_scope_keeps_expansion_and_restores_categories(self):
        with supplier_migration_state(connection):
            self.assertIn(SUPPLIER, self.applied())
            self.assertNotIn(CATEGORY, self.applied())
            self.assertNotIn(CATEGORY_ASSIGNMENT, self.applied())
        self.assertEqual(self.applied(), self.initial)
        self.assertEqual(schema_snapshot(connection), self.schema)

    def test_other_connection_transaction_is_rejected_before_migration(self):
        from django.db import connections
        other = connections['default'].copy(alias='isolation_probe')
        try:
            other.ensure_connection()
            other.set_autocommit(False)
            with other.cursor() as cursor:
                cursor.execute('SELECT 1')
            with self.assertRaisesRegex(MigrationIsolationError, 'otras transacciones'):
                with customer_migration_state(connection):
                    self.fail('No debe entrar mientras otra conexión tiene una transacción.')
        finally:
            other.rollback()
            other.close()
        self.assertEqual(self.applied(), self.initial)

    def test_repeated_blocks_do_not_contaminate_the_following_class(self):
        for _ in range(2):
            with customer_migration_state(connection):
                self.assertNotIn(SUPPLIER, self.applied())
            self.assertEqual(self.applied(), self.initial)
            self.assertEqual(schema_snapshot(connection), self.schema)
        # El siguiente consumidor usa el modelo actual, con company disponible.
        from people.models import Supplier
        self.assertEqual(list(Supplier.objects.values_list('company_id', flat=True)), [])


class MigrationIsolationSafetyTests(SimpleTestCase):
    def test_wrong_database_and_engine_are_rejected_without_connecting(self):
        for vendor, name in [('postgresql', 'sisadmi_erp_dev'), ('sqlite', 'test_fake')]:
            with self.subTest(vendor=vendor, database=name):
                bad = SimpleNamespace(vendor=vendor, settings_dict={'NAME': name})
                with self.assertRaises(MigrationIsolationError):
                    require_test_connection(bad)

    def test_mirrored_database_is_rejected(self):
        bad = SimpleNamespace(vendor='postgresql', settings_dict={
            'NAME': 'test_mirror', 'TEST': {'MIRROR': 'default'}})
        with self.assertRaises(MigrationIsolationError):
            require_test_connection(bad)

    def test_unexpected_descendant_or_dependency_rejected_before_execution(self):
        for app, name, reverse in [('people', '0007_future', True),
                                   ('purchases', '0007_future', True),
                                   (*SUPPLIER, False)]:
            with self.subTest(app=app, name=name, reverse=reverse):
                with self.assertRaises(MigrationIsolationError):
                    validate_plan([(Migration(name, app), reverse)], {SUPPLIER}, True)

    def test_parallel_customer_execution_is_rejected(self):
        runner = MigrationIsolationRunner(verbosity=0, parallel=2)
        with self.assertRaisesRegex(MigrationIsolationError, '--parallel=1'):
            runner.build_suite(['people.tests.test_customer_company_green'])

    def test_chunk_finishes_class_teardown_before_next_chunk(self):
        events = []

        class First(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                events.append('first setup')

            def test_body(self):
                events.append('first body')

            @classmethod
            def tearDownClass(cls):
                events.append('first teardown')

        class Second(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                events.append('second setup')

            def test_body(self):
                events.append('second body')

            @classmethod
            def tearDownClass(cls):
                events.append('second teardown')

        result = unittest.TestResult()
        suite = MigrationIsolatedSuite([(None, [First('test_body')]),
                                        (None, [Second('test_body')])])
        suite.run(result)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(result.testsRun, 2)
        self.assertEqual(events, ['first setup', 'first body', 'first teardown',
                                  'second setup', 'second body', 'second teardown'])
