"""Fail-closed configuration checks; no PostgreSQL connection is opened."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from django.core.exceptions import ImproperlyConfigured
from core.testing import geo01_guard as guard
from core.testing.geo01_postgresql.creation import DatabaseCreation


class Geo01EnvironmentTests(unittest.TestCase):
    def config(self):
        return dict(ENGINE=guard.ENGINE, NAME=guard.BOOTSTRAP, USER=guard.USER,
                    PASSWORD='configuration-test-placeholder', HOST=guard.HOST, PORT=guard.PORT,
                    OPTIONS={'connect_timeout': 5, 'sslmode': 'disable'},
                    TEST={'NAME': guard.TEST_DATABASE, 'MIRROR': None, 'MIGRATE': True})

    def test_only_bootstrap_and_dedicated_database_are_accepted(self):
        database = self.config()
        guard.validate_connections({'default': database}, [])
        database['NAME'] = guard.TEST_DATABASE
        guard.validate_database(database)

    def test_populated_test_and_dev_are_rejected(self):
        for name in ['test_sisadmi_erp', 'sisadmi_erp_dev', 'postgres']:
            with self.subTest(name=name):
                database = self.config(); database['NAME'] = name
                with self.assertRaises(ImproperlyConfigured): guard.validate_database(database)

    def test_aliases_mirrors_and_routers_are_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            guard.validate_connections({'default': self.config(), 'other': self.config()}, [])
        database = self.config(); database['TEST']['MIRROR'] = 'default'
        with self.assertRaises(ImproperlyConfigured): guard.validate_database(database)
        with self.assertRaises(ImproperlyConfigured): guard.validate_connections({'default': self.config()}, ['router'])

    def test_creation_checks_precreated_database_without_create_or_drop(self):
        creation = DatabaseCreation(SimpleNamespace(settings_dict=self.config()))
        cursor = Mock(); cursor.fetchone.side_effect = [(guard.USER,), (False,)*5, None]
        creation._execute_create_test_db(cursor, {'dbname': '"'+guard.TEST_DATABASE+'"'}, keepdb=True)
        self.assertEqual(cursor.execute.call_count, 3)
        self.assertTrue(all(call.args[0].lstrip().startswith('SELECT') for call in cursor.execute.call_args_list))

    def test_drop_clone_and_non_keepdb_are_rejected(self):
        creation = DatabaseCreation(SimpleNamespace(settings_dict=self.config()))
        with self.assertRaises(ImproperlyConfigured): creation._destroy_test_db(guard.TEST_DATABASE, 0)
        with self.assertRaises(ImproperlyConfigured): creation._clone_test_db('1', 0)
        cursor = Mock()
        with self.assertRaises(ImproperlyConfigured):
            creation._execute_create_test_db(cursor, {'dbname': guard.TEST_DATABASE}, keepdb=False)
        cursor.execute.assert_not_called()
