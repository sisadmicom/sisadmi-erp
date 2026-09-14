from importlib import import_module

from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class FiscalSequenceMigrationTests(TransactionTestCase):
    before = [('sri', '0004_sricertificate')]
    target = [('sri', '0005_fiscal_sequence')]

    def setUp(self):
        executor = MigrationExecutor(connection)
        self.latest = executor.loader.graph.leaf_nodes()
        apps = executor.loader.project_state(self.latest).apps
        self.assertFalse(apps.get_model('sri', 'ElectronicDocument').objects.exists())
        self.assertFalse(apps.get_model('sri', 'FiscalSequence').objects.exists())
        # Test-only reset of an EMPTY database: production migration stays
        # irreversible. Do not use this override for a database with reservations.
        migration = executor.loader.get_migration(*self.target[0])
        self.assertFalse(migration.operations[1].reversible)
        migration.operations[1].reverse_code = migrations.RunPython.noop
        try:
            executor.migrate(self.before)
        finally:
            migration.operations[1].reverse_code = None
        self.apps = executor.loader.project_state(self.before).apps
        self.addCleanup(self.restore_schema)
        person = self.apps.get_model('people', 'Person').objects.create(
            identification='1790000001001', full_name='Migración',
        )
        self.company = self.apps.get_model('core', 'Company').objects.create(person=person)
        self.branch = self.apps.get_model('core', 'Branch').objects.create(
            company=self.company, code='001', name='Matriz',
        )
        self.content_type, _ = self.apps.get_model('contenttypes', 'ContentType').objects.get_or_create(
            app_label='sales', model='sale',
        )
        self.documents = self.apps.get_model('sri', 'ElectronicDocument').objects

    def restore_schema(self):
        # Remove deliberately invalid historical fixtures before replaying schema.
        self.apps.get_model('sri', 'ElectronicDocument').objects.all().delete()
        MigrationExecutor(connection).migrate(self.latest)

    def historical(self, sequential, **overrides):
        values = dict(company=self.company, branch=self.branch,
                      content_type=self.content_type, object_id=self.documents.count() + 1,
                      document_type='01', environment='1', emission_type='1',
                      establishment='001', emission_point='001', sequential=sequential,
                      numeric_code='12345678', status='DRAFT')
        return self.documents.create(**(values | overrides))

    def migrate(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.target)
        return executor.loader.project_state(self.target).apps.get_model('sri', 'FiscalSequence')

    def assert_abort(self, message):
        original = list(self.documents.order_by('id').values())
        with self.assertRaisesMessage(RuntimeError, message):
            self.migrate()
        self.assertNotIn('sri_fiscalsequence', connection.introspection.table_names())
        self.assertEqual(list(self.documents.order_by('id').values()), original)
        self.assertNotIn(self.target[0], MigrationExecutor(connection).loader.applied_migrations)

    def test_empty_history_creates_no_counters(self):
        self.assertEqual(self.migrate().objects.count(), 0)

    def test_backfill_all_statuses_environments_and_scopes(self):
        self.historical('000000001')
        self.historical('000000002', status='ERROR', environment='2')
        self.historical('000000025', status='AUTHORIZED', is_active=False)
        self.historical('000000007', emission_point='002')
        self.historical('000000009', document_type='04')
        self.historical('999999999', establishment='002')
        counters = self.migrate().objects
        self.assertEqual(counters.count(), 4)
        self.assertEqual(counters.get(establishment='001', emission_point='001', document_type='01').next_number, 26)
        self.assertEqual(counters.get(emission_point='002').next_number, 8)
        self.assertEqual(counters.get(document_type='04').next_number, 10)
        self.assertEqual(counters.get(establishment='002').next_number, 1000000000)

    def test_invalid_sequential_aborts_without_partial_writes(self):
        self.historical('000000025')
        bad = self.historical('000000026', emission_point='002')
        for value in ('', '00000000A', '000000000', '123', '１２３４５６７８９', '00000001\n'):
            with self.subTest(value=repr(value)):
                self.documents.filter(pk=bad.pk).update(sequential=value)
                self.assert_abort('históric' if value == '000000000' else 'Historia fiscal inválida')

    def test_invalid_codes_abort_without_partial_writes(self):
        self.historical('000000025')
        bad = self.historical('000000026')
        for field, value in (('establishment', 'A01'), ('emission_point', ' 01'),
                             ('document_type', '1'), ('document_type', '0\n')):
            with self.subTest(field=field):
                self.documents.filter(pk=bad.pk).update(establishment='001', emission_point='001', document_type='01')
                self.documents.filter(pk=bad.pk).update(**{field: value})
                self.assert_abort('Historia fiscal inválida')

    def test_duplicate_origin_aborts_before_constraint(self):
        first = self.historical('000000001')
        self.historical('000000002', object_id=first.object_id)
        self.assert_abort('Origen electrónico duplicado')

    def test_unexpected_counter_is_not_overwritten(self):
        self.historical('000000025')
        model = self.migrate()
        before = list(model.objects.values())
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(self.target).apps
        migration = import_module('sri.migrations.0005_fiscal_sequence')
        with connection.schema_editor() as editor:
            with self.assertRaisesMessage(RuntimeError, 'FiscalSequence preexistente'):
                migration.preflight_and_backfill(apps, editor)
        self.assertEqual(list(model.objects.values()), before)
