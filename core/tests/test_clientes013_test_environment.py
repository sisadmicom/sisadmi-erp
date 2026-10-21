"""Unit tests only: no Django setup, model imports or network connections."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.core.exceptions import ImproperlyConfigured
from core.testing import clientes013_guard as guard
from core.testing.clientes013_postgresql.base import DatabaseWrapper
from core.testing.clientes013_postgresql.creation import DatabaseCreation
from core.testing.clientes013_runner import Clientes013TestRunner, MODULES
from django.test.runner import DiscoverRunner


class Clientes013EnvironmentTests(unittest.TestCase):
    def config(self):
        return {'ENGINE':guard.ENGINE,'NAME':guard.DATABASE,'USER':guard.USER,
                'PASSWORD':'unit-test-placeholder','HOST':guard.HOST,'PORT':guard.PORT,
                'OPTIONS':{'connect_timeout':5,'sslmode':'disable'},
                'TEST':{'NAME':guard.DATABASE,'MIRROR':None,'MIGRATE':True}}

    def test_exact_configuration_accepted(self):
        guard.validate_connections({'default':self.config()}, [])

    def test_every_other_database_rejected(self):
        for name in ['test_sisadmi_erp','sisadmi_erp_dev','test_sisadmi_geo01',
                     'sisadmi_erp_test_bootstrap','postgres','',guard.DATABASE+'_1']:
            with self.subTest(name=name):
                cfg=self.config();cfg['NAME']=name
                with self.assertRaises(ImproperlyConfigured):guard.validate_database(cfg)

    def test_wrong_user_host_port_and_engine_rejected(self):
        for key,value in [('USER','postgres'),('HOST','localhost'),('PORT','5433'),
                          ('ENGINE','django.db.backends.postgresql'),('PASSWORD','')]:
            with self.subTest(key=key):
                cfg=self.config();cfg[key]=value
                with self.assertRaises(ImproperlyConfigured):guard.validate_database(cfg)

    def test_mirrors_alternate_test_target_and_disabled_migrations_rejected(self):
        for change in [{'MIRROR':'other'},{'NAME':'test_sisadmi_erp'},{'MIGRATE':False}]:
            cfg=self.config();cfg['TEST'].update(change)
            with self.assertRaises(ImproperlyConfigured):guard.validate_database(cfg)

    def test_aliases_and_routers_rejected(self):
        for alias in ['other','__no_db__','isolation_probe','con532_row_probe']:
            with self.assertRaises(ImproperlyConfigured):guard.validate_database(self.config(),alias)
        with self.assertRaises(ImproperlyConfigured):
            guard.validate_connections({'default':self.config(),'other':self.config()},[])
        with self.assertRaises(ImproperlyConfigured):guard.validate_connections({'default':self.config()},['router'])

    def test_pooling_persistence_and_parameter_overrides_rejected(self):
        for key,value in [('CONN_MAX_AGE',60),('CONN_HEALTH_CHECKS',True),
                          ('OPTIONS',{'connect_timeout':5,'sslmode':'disable','pool':True})]:
            cfg=self.config();cfg[key]=value
            with self.assertRaises(ImproperlyConfigured):guard.validate_database(cfg)

    def test_execution_requires_explicit_future_authorization(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ImproperlyConfigured):guard.require_execution()
        with patch.dict(os.environ,{'CLIENTES013_ALLOW_TEST_EXECUTION':'1'},clear=True):guard.require_execution()
        with patch.dict(os.environ,{'CLIENTES013_ALLOW_TEST_EXECUTION':'1','PGOPTIONS':'unsafe'},clear=True):
            with self.assertRaises(ImproperlyConfigured):guard.require_execution()

    def cursor(self):
        cursor=Mock();cursor.fetchone.side_effect=[(guard.DATABASE,guard.USER,'127.0.0.1/32',5432),
            (guard.USER,),(False,)*5,None,(True,True)]
        return cursor

    def test_real_identity_owner_role_and_permissions_contract(self):
        cursor=self.cursor();guard.verify_identity(cursor)
        self.assertEqual(cursor.execute.call_count,5)
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in cursor.execute.call_args_list))

    def test_identity_owner_privileges_membership_and_permissions_fail_closed(self):
        valid=[(guard.DATABASE,guard.USER,'127.0.0.1/32',5432),(guard.USER,),(False,)*5,None,(True,True)]
        for index,replacement in [(0,('test_sisadmi_erp',guard.USER,'127.0.0.1/32',5432)),
            (1,('postgres',)),(2,(True,False,False,False,False)),(3,(1,)),(4,(True,False))]:
            values=list(valid);values[index]=replacement;cursor=Mock();cursor.fetchone.side_effect=values
            with self.assertRaises(ImproperlyConfigured):guard.verify_identity(cursor)

    def test_backend_rejects_before_opening_network(self):
        wrapper=SimpleNamespace(settings_dict=self.config(),alias='default')
        with patch.dict(os.environ,{},clear=True), patch('django.db.backends.postgresql.base.DatabaseWrapper.get_new_connection') as connect:
            with self.assertRaises(ImproperlyConfigured):DatabaseWrapper.get_new_connection(wrapper,{})
            connect.assert_not_called()
        wrapper.settings_dict['NAME']='test_sisadmi_erp'
        with self.assertRaises(ImproperlyConfigured):DatabaseWrapper.get_connection_params(wrapper)

    def test_backend_rejects_libpq_override_before_network(self):
        wrapper=SimpleNamespace(settings_dict=self.config(),alias='default')
        params={'dbname':guard.DATABASE,'user':guard.USER,'password':'unit-test-placeholder',
                'host':guard.HOST,'port':guard.PORT,'connect_timeout':5,'sslmode':'disable','service':'other'}
        with patch.dict(os.environ,{'CLIENTES013_ALLOW_TEST_EXECUTION':'1'},clear=True), patch('django.db.backends.postgresql.base.DatabaseWrapper.get_new_connection') as connect:
            with self.assertRaises(ImproperlyConfigured):DatabaseWrapper.get_new_connection(wrapper,params)
            connect.assert_not_called()

    def test_creation_drop_clone_and_bootstrap_operations_forbidden(self):
        creation=DatabaseCreation(SimpleNamespace(settings_dict=self.config(),alias='default'))
        for name in ['_execute_create_test_db','_destroy_test_db','_clone_test_db']:
            with self.assertRaises(ImproperlyConfigured):getattr(creation,name)()
        with self.assertRaises(ImproperlyConfigured):DatabaseWrapper._nodb_cursor(None)
        with self.assertRaises(ImproperlyConfigured):creation.destroy_test_db(keepdb=False)

    def test_setup_cannot_migrate_before_execution_authorized(self):
        creation=DatabaseCreation(SimpleNamespace(settings_dict=self.config(),alias='default'))
        with patch.dict(os.environ,{},clear=True), patch('core.testing.clientes013_postgresql.creation.call_command') as command:
            with self.assertRaises(ImproperlyConfigured):creation.create_test_db(keepdb=True)
            command.assert_not_called()

    def test_runner_rejects_parallel_or_non_keepdb(self):
        runner=object.__new__(Clientes013TestRunner)
        fake=SimpleNamespace(DATABASES={'default':self.config()},DATABASE_ROUTERS=[])
        with patch('core.testing.clientes013_runner.settings',fake), patch.dict(os.environ,{'CLIENTES013_ALLOW_TEST_EXECUTION':'1'},clear=True), patch.object(DiscoverRunner,'run_tests') as run:
            for keepdb,parallel in [(False,1),(True,2),(True,0)]:
                runner.keepdb=keepdb;runner.parallel=parallel
                with self.assertRaises(ImproperlyConfigured):runner.run_tests([])
            run.assert_not_called()

    def test_runner_whitelist_is_exact_and_excludes_frozen_modules(self):
        self.assertEqual(MODULES,frozenset({
            'people.tests.test_customer_document_restrictions_clientes013',
            'people.tests.test_customer_document_concurrency_clientes013',
            'people.tests.test_customer_category_assignment',
            'people.tests.test_customer_ui_actions',
            'people.tests.test_customer_person_replacement'}))
        self.assertFalse(any('geo01' in m or 'cat023' in m for m in MODULES))

    def test_runner_rejects_unknown_labels_before_collection(self):
        runner=object.__new__(Clientes013TestRunner)
        with patch.object(DiscoverRunner,'build_suite') as build:
            for labels in [None, [], ['people'], ['people.tests.test_geo01_import'],
                           ['people.tests.test_commercial_document_concurrency_cat023_red']]:
                with self.assertRaises(ImproperlyConfigured):runner.build_suite(labels)
            build.assert_not_called()

    def test_catalog_uses_only_required_official_types(self):
        from core.testing.clientes013_catalog import REQUIRED_KINDS
        from people.constants.identification_type import IdentificationType
        self.assertEqual(REQUIRED_KINDS, (IdentificationType.OTHER, IdentificationType.PASSPORT))
        self.assertEqual([(x.value, x.label) for x in REQUIRED_KINDS],
                         [('OTHER', 'Otro'), ('PASSPORT', 'Pasaporte')])

    def test_catalog_rejects_unauthorized_execution_before_model_or_connection_access(self):
        from core.testing import clientes013_catalog as catalog
        with patch.dict(os.environ, {}, clear=True), patch.object(catalog.apps, 'get_model') as model, patch.object(catalog, 'connections') as connections:
            with self.assertRaises(ImproperlyConfigured):
                catalog.initialize_required_kinds(None, using='default')
            model.assert_not_called(); connections.__getitem__.assert_not_called()

    def test_catalog_rejects_alternate_alias_before_opening_connection(self):
        from core.testing import clientes013_catalog as catalog
        with patch.dict(os.environ, {'CLIENTES013_ALLOW_TEST_EXECUTION':'1'}, clear=True), patch.object(catalog, 'connections') as connections:
            for alias in ['other', '__no_db__', 'isolation_probe']:
                with self.assertRaises(ImproperlyConfigured):
                    catalog.initialize_required_kinds(None, using=alias)
            connections.__getitem__.assert_not_called()

    def test_catalog_signal_is_scoped_and_disconnected_on_error(self):
        from core.testing import clientes013_catalog as catalog
        fake = SimpleNamespace(DATABASES={'default':self.config()}, DATABASE_ROUTERS=[])
        for fail in [False, True]:
            with self.subTest(fail=fail), patch.object(catalog, 'settings', fake), patch.object(catalog.apps, 'get_app_config', return_value=object()) as app, patch.object(catalog, 'post_migrate') as signal, patch.dict(os.environ, {'CLIENTES013_ALLOW_TEST_EXECUTION':'1'}, clear=True):
                try:
                    with catalog.scoped_identification_catalog():
                        signal.connect.assert_called_once()
                        signal.disconnect.assert_not_called()
                        if fail: raise RuntimeError('test-only failure')
                except RuntimeError:
                    if not fail: raise
                kw = signal.connect.call_args.kwargs
                signal.disconnect.assert_called_once_with(sender=kw['sender'], dispatch_uid=kw['dispatch_uid'])
                self.assertIs(signal.connect.call_args.args[0], catalog.initialize_required_kinds)
                self.assertFalse(kw['weak'])

    def test_runner_scopes_catalog_for_success_and_failure(self):
        from contextlib import contextmanager
        fake = SimpleNamespace(DATABASES={'default':self.config()}, DATABASE_ROUTERS=[])
        runner = object.__new__(Clientes013TestRunner); runner.keepdb=True; runner.parallel=1
        for fail in [False, True]:
            events=[]
            @contextmanager
            def scoped():
                events.append('enter')
                try: yield
                finally: events.append('exit')
            with self.subTest(fail=fail), patch('core.testing.clientes013_runner.settings', fake), patch('core.testing.clientes013_runner.scoped_identification_catalog', scoped), patch.dict(os.environ, {'CLIENTES013_ALLOW_TEST_EXECUTION':'1'}, clear=True), patch.object(DiscoverRunner, 'run_tests', side_effect=RuntimeError('test-only failure') if fail else None, return_value=0):
                if fail:
                    with self.assertRaises(RuntimeError): runner.run_tests(['authorized-label'])
                else: self.assertEqual(runner.run_tests(['authorized-label']), 0)
                self.assertEqual(events, ['enter', 'exit'])
