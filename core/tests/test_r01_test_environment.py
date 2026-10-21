"""Security/configuration tests with no Django setup or PostgreSQL connections."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLWrapper

from core.testing.r01_guard import (
    BOOTSTRAP, ENGINE, HOST, PORT, TEST_DATABASE, USER,
    required_environment, validate_connections, validate_database,
)
from core.testing.r01_postgresql.base import DatabaseWrapper
from core.testing.r01_postgresql.creation import DatabaseCreation
from core.testing.r01_runner import R01TestRunner
from core.testing.runner import MigrationIsolationRunner


def database():
    return {
        "ENGINE": ENGINE, "NAME": BOOTSTRAP, "USER": USER,
        "PASSWORD": "synthetic-unit-test-value", "HOST": HOST, "PORT": PORT,
        "CONN_MAX_AGE": 0, "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {"connect_timeout": 5, "sslmode": "disable"},
        "TEST": {"NAME": TEST_DATABASE, "MIRROR": None, "MIGRATE": True},
    }


class R01EnvironmentTests(unittest.TestCase):
    def test_only_explicit_r01_destinations_are_allowed(self):
        for name in (BOOTSTRAP, TEST_DATABASE):
            value = database()
            value["NAME"] = name
            validate_connections({"default": value}, [])
        value["NAME"] = BOOTSTRAP
        validate_database(value, "__no_db__", maintenance=True)
        for name in (None, "postgres", TEST_DATABASE):
            value["NAME"] = name
            with self.subTest(maintenance_name=name), self.assertRaises(ImproperlyConfigured):
                validate_database(value, "__no_db__", maintenance=True)

    def test_dev_host_user_port_and_overrides_are_rejected(self):
        for key, value in (
            ("NAME", "sisadmi_erp_dev"), ("NAME", ""), ("NAME", None),
            ("USER", "sisadmi_erp"), ("HOST", "localhost"), ("HOST", ""),
            ("PORT", "5433"), ("PASSWORD", ""),
            ("ENGINE", "django.db.backends.postgresql"), ("CONN_MAX_AGE", 60),
            ("OPTIONS", {"service": "development"}),
            ("OPTIONS", {"pool": True}),
        ):
            with self.subTest(key=key, value=value):
                candidate = database()
                candidate[key] = value
                with self.assertRaises(ImproperlyConfigured):
                    validate_connections({"default": candidate}, [])

    def test_aliases_routers_mirrors_and_test_name_overrides_are_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_connections({"default": database(), "dev": database()}, [])
        with self.assertRaises(ImproperlyConfigured):
            validate_connections({"default": database()}, ["a.router"])
        for key, value in (("NAME", "sisadmi_erp_dev"), ("MIRROR", "dev"), ("MIGRATE", False)):
            candidate = database()
            candidate["TEST"][key] = value
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                validate_connections({"default": candidate}, [])

    def test_auxiliary_connections_are_limited_to_existing_test_probes(self):
        for alias in ("isolation_probe", "con532_row_probe"):
            candidate = database()
            candidate["NAME"] = TEST_DATABASE
            validate_database(candidate, alias)
            candidate["NAME"] = BOOTSTRAP
            with self.assertRaises(ImproperlyConfigured):
                validate_database(candidate, alias)
        with self.assertRaises(ImproperlyConfigured):
            validate_connections({"default": database(), "isolation_probe": database()}, [])

    def test_missing_r01_password_never_uses_dev_password(self):
        with patch.dict(os.environ, {"DJANGO_DB_PASSWORD": "synthetic-dev-value"}, clear=True):
            with self.assertRaises(ImproperlyConfigured):
                required_environment("R01_TEST_DB_PASSWORD")

    def test_guard_precedes_any_driver_connection(self):
        wrapper = DatabaseWrapper(database())
        with patch.object(PostgreSQLWrapper, "get_new_connection") as connect:
            for params in (
                {"dbname": "sisadmi_erp_dev"},
                {"dbname": TEST_DATABASE, "hostaddr": "192.0.2.1"},
            ):
                with self.assertRaises(ImproperlyConfigured):
                    wrapper.get_new_connection(params)
            connect.assert_not_called()

    def test_operator_gate_and_libpq_environment_precede_driver(self):
        wrapper = DatabaseWrapper(database())
        params = {
            "dbname": BOOTSTRAP, "user": USER, "host": HOST, "port": PORT,
            "password": database()["PASSWORD"], "sslmode": "disable", "connect_timeout": 5,
        }
        with patch.object(PostgreSQLWrapper, "get_new_connection") as connect:
            for env in ({}, {"R01_TEST_ADMIN_VERIFIED": "1", "PGHOSTADDR": "192.0.2.1"}):
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(ImproperlyConfigured):
                        wrapper.get_new_connection(params)
            connect.assert_not_called()

    def test_administrative_and_bootstrap_connections_are_read_only(self):
        for name, alias in ((BOOTSTRAP, "default"), (TEST_DATABASE, "default"), (BOOTSTRAP, "__no_db__")):
            config = database()
            config["NAME"] = name
            wrapper = DatabaseWrapper(config, alias=alias)
            params = {
                "dbname": name, "user": USER, "host": HOST, "port": PORT,
                "password": config["PASSWORD"], "sslmode": "disable", "connect_timeout": 5,
            }
            with patch.dict(os.environ, {"R01_TEST_ADMIN_VERIFIED": "1"}, clear=True):
                with patch.object(PostgreSQLWrapper, "get_new_connection") as connect:
                    wrapper.get_new_connection(params)
                    expected = "" if name == TEST_DATABASE else "-c default_transaction_read_only=on"
                    self.assertEqual(connect.call_args.args[0]["options"], expected)

    def test_precreated_keepdb_never_emits_create_database(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [(USER,), (False,) * 5, None]
        creation = DatabaseCreation(SimpleNamespace())
        creation._execute_create_test_db(cursor, {"dbname": '"test_sisadmi_erp"'}, keepdb=True)
        self.assertEqual(cursor.execute.call_count, 3)
        self.assertTrue(all(c.args[0].startswith("SELECT ") for c in cursor.execute.call_args_list))

    def test_missing_test_database_and_privileged_role_are_rejected(self):
        for rows in ([None], [("another_owner",)], [(USER,), (True, False, False, False, False)], [(USER,), (False,) * 5, (1,)]):
            cursor = Mock()
            cursor.fetchone.side_effect = rows
            with self.subTest(rows=rows), self.assertRaises(ImproperlyConfigured):
                DatabaseCreation(SimpleNamespace())._execute_create_test_db(
                    cursor, {"dbname": TEST_DATABASE}, keepdb=True
                )

    def test_no_keepdb_drop_and_clone_are_rejected(self):
        creation = DatabaseCreation(SimpleNamespace())
        cursor = Mock()
        with self.assertRaises(ImproperlyConfigured):
            creation._execute_create_test_db(cursor, {"dbname": TEST_DATABASE}, keepdb=False)
        cursor.execute.assert_not_called()
        with self.assertRaises(ImproperlyConfigured):
            creation._destroy_test_db(TEST_DATABASE, 0)
        with self.assertRaises(ImproperlyConfigured):
            creation._clone_test_db("1", 0, keepdb=True)

    def test_runner_requires_keepdb_and_one_process_before_setup(self):
        settings = SimpleNamespace(DATABASES={"default": database()}, DATABASE_ROUTERS=[])
        with patch("core.testing.r01_runner.settings", settings):
            with patch.object(MigrationIsolationRunner, "run_tests") as execute:
                for keepdb, parallel in ((False, 1), (True, 2), (True, 0)):
                    with self.subTest(keepdb=keepdb, parallel=parallel):
                        runner = R01TestRunner(keepdb=keepdb, parallel=parallel)
                        with self.assertRaises(ImproperlyConfigured):
                            runner.run_tests(["catalog"])
                execute.assert_not_called()

    def test_runner_preserves_historical_runner_with_safe_options(self):
        settings = SimpleNamespace(DATABASES={"default": database()}, DATABASE_ROUTERS=[])
        with patch("core.testing.r01_runner.settings", settings):
            with patch.object(MigrationIsolationRunner, "run_tests", return_value=0) as execute:
                result = R01TestRunner(keepdb=True, parallel=1).run_tests(["catalog"])
                self.assertEqual(result, 0)
                execute.assert_called_once_with(["catalog"])
