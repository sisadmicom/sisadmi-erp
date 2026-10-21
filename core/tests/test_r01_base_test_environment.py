"""R-01 Base unit contracts. No Django setup and no database/network access."""
import ast
import importlib
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.postgresql.creation import DatabaseCreation as PostgreSQLCreation
from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLWrapper
from django.db.backends.base.base import BaseDatabaseWrapper
from django.test.runner import DiscoverRunner

from core.testing import r01_base_guard as guard
from core.testing.r01_base_postgresql.base import DatabaseWrapper
from core.testing.r01_base_postgresql.creation import DatabaseCreation
from core.testing.r01_base_runner import R01BaseTestRunner


def database():
    return {"ENGINE": guard.ENGINE, "NAME": guard.DATABASE, "USER": guard.USER,
            "PASSWORD": "synthetic-unit-value", "HOST": guard.HOST, "PORT": guard.PORT,
            "CONN_MAX_AGE": 0, "CONN_HEALTH_CHECKS": False,
            "OPTIONS": dict(guard.OPTIONS),
            "TEST": {"NAME": guard.DATABASE, "MIRROR": None, "MIGRATE": True}}


def identity_rows():
    return [(guard.DATABASE, guard.USER, guard.USER, "127.0.0.1/32", 5432),
            (guard.USER,), (False,) * 5, None, (True, True)]


class R01BaseEnvironmentTests(unittest.TestCase):
    def setUp(self):
        # Defense in depth: even a missing driver mock cannot open a connection.
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"R01_BASE_ALLOW_TEST_EXECUTION": "1"}, clear=True).start()
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")).start()
        self.driver = patch.object(PostgreSQLWrapper, "get_new_connection",
                                   side_effect=AssertionError("PostgreSQL forbidden")).start()
        patch.object(BaseDatabaseWrapper, "ensure_connection",
                     side_effect=AssertionError("Django connection forbidden")).start()

    def test_valid_closed_configuration(self):
        guard.validate_connections({"default": database()}, [])

    def test_protected_destinations_and_unknown_names_rejected(self):
        for name in ["test_sisadmi_erp", "sisadmi_erp_dev", "test_sisadmi_geo01",
                     "test_sisadmi_clientes013", "sisadmi_erp_test_bootstrap",
                     "postgres", "test_sisadmi_cat05", "test_sisadmi_r01_1", "unknown", "", None]:
            for key in ["NAME", "TEST.NAME"]:
                with self.subTest(name=name, key=key):
                    cfg = database()
                    if key == "NAME": cfg[key] = name
                    else: cfg["TEST"]["NAME"] = name
                    with self.assertRaises(ImproperlyConfigured): guard.validate_database(cfg)
        self.driver.assert_not_called()

    def test_wrong_endpoint_role_backend_and_credentials_rejected(self):
        for key, value in [("USER", "postgres"), ("HOST", "localhost"), ("HOST", ""),
                           ("HOST", "/var/run/postgresql"), ("PORT", "5433"),
                           ("ENGINE", "django.db.backends.postgresql"), ("PASSWORD", ""),
                           ("CONN_MAX_AGE", 1), ("CONN_HEALTH_CHECKS", True)]:
            with self.subTest(key=key):
                cfg = database(); cfg[key] = value
                with self.assertRaises(ImproperlyConfigured): guard.validate_database(cfg)

    def test_aliases_routers_mirrors_and_migration_overrides_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            guard.validate_connections({"default": database(), "other": database()}, [])
        with self.assertRaises(ImproperlyConfigured):
            guard.validate_connections({"default": database()}, ["router"])
        for alias in ["__no_db__", "isolation_probe", "con532_row_probe", "other"]:
            with self.subTest(alias=alias), self.assertRaises(ImproperlyConfigured):
                guard.validate_database(database(), alias)
        for key, value in [("MIRROR", "default"), ("MIGRATE", False),
                           ("DEPENDENCIES", ["other"]), ("TEMPLATE", "template0")]:
            cfg = database(); cfg["TEST"][key] = value
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                guard.validate_database(cfg)

    def test_libpq_and_pool_options_rejected(self):
        for options in [{"pool": True}, {"service": "dev"}, {**guard.OPTIONS, "hostaddr": "127.0.0.2"},
                        {**guard.OPTIONS, "options": "-c role=postgres"}]:
            cfg = database(); cfg["OPTIONS"] = options
            with self.subTest(options=options), self.assertRaises(ImproperlyConfigured):
                guard.validate_database(cfg)

    def test_password_has_no_legacy_or_dev_fallback(self):
        with patch.dict(os.environ, {"R01_TEST_DB_PASSWORD": "synthetic-old",
                                    "DJANGO_DB_PASSWORD": "synthetic-dev"}, clear=True):
            with self.assertRaises(ImproperlyConfigured): guard.password()
        for value in ["", "x\ny", "x\ry", "x\x00y"]:
            with patch.object(guard.os, "environ", {"R01_BASE_TEST_DB_PASSWORD": value}):
                with self.assertRaises(ImproperlyConfigured): guard.password()
        with patch.dict(os.environ, {"R01_BASE_TEST_DB_PASSWORD": "synthetic-new"}):
            self.assertEqual(guard.password(), "synthetic-new")

    def test_execution_gate_and_inherited_pg_variables_rejected(self):
        for env in [{}, {"R01_TEST_ADMIN_VERIFIED": "1"},
                    {"R01_BASE_ALLOW_TEST_EXECUTION": "1", "PGOPTIONS": ""},
                    {"R01_BASE_ALLOW_TEST_EXECUTION": "1", "PGSERVICEFILE": "unused"}]:
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ImproperlyConfigured): guard.require_execution()

    def test_identity_queries_are_select_only(self):
        cursor = Mock(); cursor.fetchone.side_effect = identity_rows()
        guard.verify_identity(cursor)
        self.assertEqual(cursor.execute.call_count, 5)
        self.assertTrue(all(c.args[0].startswith("SELECT ") for c in cursor.execute.call_args_list))

    def test_all_real_identity_mismatches_rejected(self):
        first = identity_rows()[0]
        for index, value in [(0, "test_sisadmi_erp"), (1, "postgres"), (2, "postgres"),
                             (3, "127.0.0.2/32"), (3, None), (4, 5433)]:
            row = list(first); row[index] = value
            cursor = Mock(); cursor.fetchone.return_value = tuple(row)
            with self.subTest(index=index, value=value), self.assertRaises(ImproperlyConfigured):
                guard.verify_identity(cursor)

    def test_owner_attributes_memberships_and_privileges_rejected(self):
        for index, value in [(1, ("postgres",)), (1, None), (2, (True, False, False, False, False)),
                             (2, (False, True, False, False, False)), (2, (False, False, True, False, False)),
                             (2, (False, False, False, True, False)), (2, (False, False, False, False, True)),
                             (3, (1,)), (4, (False, True)), (4, (True, False))]:
            rows = identity_rows(); rows[index] = value
            cursor = Mock(); cursor.fetchone.side_effect = rows
            with self.subTest(index=index, value=value), self.assertRaises(ImproperlyConfigured):
                guard.verify_identity(cursor)

    def params(self):
        cfg = database()
        return {"dbname": cfg["NAME"], "user": cfg["USER"], "password": cfg["PASSWORD"],
                "host": cfg["HOST"], "port": cfg["PORT"], **cfg["OPTIONS"]}

    def test_connection_parameters_checked_before_driver(self):
        wrapper = DatabaseWrapper(database())
        for key, value in [("dbname", "test_sisadmi_erp"), ("user", "postgres"),
                           ("host", "127.0.0.2"), ("port", "5433"), ("password", "different"),
                           ("sslmode", "prefer"), ("connect_timeout", 30),
                           ("hostaddr", "127.0.0.2"), ("service", "dev"), ("options", "")]:
            params = self.params(); params[key] = value
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                wrapper.get_new_connection(params)
        self.driver.assert_not_called()

    def raw(self, rows=None):
        raw = Mock()
        raw.cursor.return_value.__enter__ = Mock(return_value=Mock())
        raw.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor = raw.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = identity_rows() if rows is None else rows
        return raw

    def test_every_physical_connection_attested_and_rolled_back(self):
        raws = [self.raw(), self.raw()]
        self.driver.side_effect = raws
        wrapper = DatabaseWrapper(database())
        for raw in raws:
            self.assertIs(wrapper.get_new_connection(self.params()), raw)
            raw.rollback.assert_called_once_with(); raw.close.assert_not_called()
            self.assertEqual(raw.cursor.return_value.__enter__.return_value.execute.call_count, 5)
        self.assertEqual(self.driver.call_count, 2)
        self.assertEqual(self.driver.call_args.args[0]["options"], "")

    def test_bad_identity_closes_connection_and_preserves_error(self):
        raw = self.raw([( "sisadmi_erp_dev", guard.USER, guard.USER, "127.0.0.1", 5432)])
        self.driver.side_effect = None; self.driver.return_value = raw
        with self.assertRaises(ImproperlyConfigured):
            DatabaseWrapper(database()).get_new_connection(self.params())
        raw.close.assert_called_once_with(); raw.rollback.assert_not_called()

    def test_identity_query_error_closes_and_propagates(self):
        raw = self.raw(); error = RuntimeError("synthetic-query-error")
        raw.cursor.return_value.__enter__.return_value.execute.side_effect = error
        self.driver.side_effect = None; self.driver.return_value = raw
        with self.assertRaises(RuntimeError) as caught:
            DatabaseWrapper(database()).get_new_connection(self.params())
        self.assertIs(caught.exception, error); raw.close.assert_called_once_with()

    def test_administrative_connection_rejected(self):
        with self.assertRaises(ImproperlyConfigured): DatabaseWrapper(database())._nodb_cursor()
        with self.assertRaises(ImproperlyConfigured): DatabaseWrapper(database(), alias="__no_db__").get_connection_params()
        self.driver.assert_not_called()

    def creation(self):
        conn = MagicMock(alias="default", settings_dict=database())
        return DatabaseCreation(conn), conn

    def settings(self):
        return SimpleNamespace(DATABASES={"default": database()}, DATABASE_ROUTERS=[])

    def test_precreated_base_check_never_issues_ddl(self):
        creation, conn = self.creation()
        with patch("core.testing.r01_base_postgresql.creation.settings", self.settings()):
            with patch("core.testing.r01_base_postgresql.creation.verify_identity") as identity:
                self.assertEqual(creation._create_test_db(0, False, keepdb=True), guard.DATABASE)
                identity.assert_called_once()
        conn.cursor.assert_called_once_with()

    def test_creation_without_keepdb_rejected_before_cursor(self):
        creation, conn = self.creation()
        with patch("core.testing.r01_base_postgresql.creation.settings", self.settings()):
            with self.assertRaises(ImproperlyConfigured): creation._create_test_db(0, False, keepdb=False)
        conn.cursor.assert_not_called()

    def test_all_database_ddl_clone_and_mirror_paths_rejected(self):
        creation, conn = self.creation()
        for name in ["_execute_create_test_db", "_destroy_test_db", "_clone_test_db",
                     "clone_test_db", "get_test_db_clone_settings", "set_as_test_mirror"]:
            with self.subTest(name=name), self.assertRaises(ImproperlyConfigured): getattr(creation, name)()
        conn.cursor.assert_not_called()

    def test_teardown_only_closes_precreated_database(self):
        creation, conn = self.creation()
        with patch("core.testing.r01_base_postgresql.creation.settings", self.settings()):
            creation.destroy_test_db(guard.DATABASE, keepdb=True)
            conn.close.assert_called_once_with()
            for kwargs in [{"keepdb": False}, {"keepdb": True, "suffix": "1"},
                           {"keepdb": True, "old_database_name": "test_sisadmi_erp"}]:
                with self.subTest(kwargs=kwargs), self.assertRaises(ImproperlyConfigured):
                    creation.destroy_test_db(**kwargs)
        conn.cursor.assert_not_called()

    def test_standard_django_setup_and_serialization_retained(self):
        creation, conn = self.creation()
        settings = self.settings()
        with patch("core.testing.r01_base_postgresql.creation.settings", settings), \
             patch("django.db.backends.base.creation.settings", settings), \
             patch.object(creation, "_create_test_db", return_value=guard.DATABASE) as preflight, \
             patch.object(creation, "serialize_db_to_string", return_value="serialized") as serialize, \
             patch("django.core.management.call_command") as command:
            result = creation.create_test_db(verbosity=0, keepdb=True, serialize=True)
        self.assertEqual(result, guard.DATABASE)
        preflight.assert_called_once_with(0, False, True)
        serialize.assert_called_once_with()
        self.assertEqual(conn._test_serialized_contents, "serialized")
        self.assertEqual([c.args[0] for c in command.call_args_list], ["migrate", "createcachetable"])
        self.assertEqual(command.call_args_list[0].kwargs["database"], "default")
        conn.ensure_connection.assert_called_once_with()

    def test_runner_inherits_only_standard_django_runner(self):
        self.assertEqual(R01BaseTestRunner.__bases__, (DiscoverRunner,))
        with patch("core.testing.r01_base_runner.settings", self.settings()), \
             patch.object(DiscoverRunner, "run_tests", return_value=0) as execute:
            self.assertEqual(R01BaseTestRunner(keepdb=True, parallel=1).run_tests(["core"]), 0)
            execute.assert_called_once_with(["core"])

    def test_runner_rejects_unsafe_options_before_setup(self):
        with patch("core.testing.r01_base_runner.settings", self.settings()), \
             patch.object(DiscoverRunner, "run_tests") as execute:
            for keepdb, parallel in [(False, 1), (True, 0), (True, 2)]:
                with self.subTest(keepdb=keepdb, parallel=parallel), self.assertRaises(ImproperlyConfigured):
                    R01BaseTestRunner(keepdb=keepdb, parallel=parallel).run_tests(["core"])
            execute.assert_not_called()

    def test_new_modules_do_not_import_old_settings_or_runners(self):
        root = Path(__file__).resolve().parents[2]
        paths = [root / "config/settings_r01_base_test.py", *root.glob("core/testing/r01_base*.py"),
                 *root.glob("core/testing/r01_base_postgresql/*.py")]
        forbidden = {"config.settings", "config.settings_test_r01", "core.testing.runner",
                     "core.testing.migration_isolation", "core.testing.r01_runner"}
        for path in paths:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom): self.assertNotIn(node.module, forbidden)

    def test_settings_import_needs_only_own_password_without_connecting(self):
        with patch.dict(os.environ, {"R01_BASE_TEST_DB_PASSWORD": "synthetic-settings-value"}, clear=True):
            module = importlib.import_module("config.settings_r01_base_test")
            module = importlib.reload(module)
            self.assertEqual(module.DATABASES["default"]["NAME"], guard.DATABASE)
            self.assertEqual(module.DATABASES["default"]["TEST"]["NAME"], guard.DATABASE)
            self.assertFalse(module._RUNTIME.exists())
        self.driver.assert_not_called(); self.network.assert_not_called()


    def serialization_probe(self):
        """Exercise Django's real serializer with real unsaved models, mock reads only."""
        import django
        from django.apps import apps
        with patch.dict(os.environ, {
            "DJANGO_SETTINGS_MODULE": "config.settings_r01_base_test",
            "R01_BASE_TEST_DB_PASSWORD": "synthetic-serialization-only",
        }):
            django.setup()
        from contextlib import ExitStack
        from people.models import Person, IdentificationKind
        person = Person(pk=101, identification="R01-SYNTHETIC", full_name="Synthetic",
                        person_type="NATURAL", identification_type="OTHER",
                        identification_kind_id=202)
        kind = IdentificationKind(pk=202, code="OTHER", name="Otro")
        ordered = [m for m in apps.get_app_config("people").get_models()
                   if m in (Person, IdentificationKind)]
        app = SimpleNamespace(models_module=object(), label="people", name="people",
                              get_models=lambda: iter(ordered))
        creation, conn = self.creation()
        with ExitStack() as stack:
            stack.enter_context(patch("django.db.backends.base.creation.apps.get_app_configs",
                                      return_value=[app]))
            stack.enter_context(patch("django.db.migrations.loader.MigrationLoader",
                                      return_value=SimpleNamespace(migrated_apps={"people"})))
            stack.enter_context(patch("django.db.backends.base.creation.router.allow_migrate_model",
                                      return_value=True))
            for model, obj in [(Person, person), (IdentificationKind, kind)]:
                stack.enter_context(patch.object(model._meta, "can_migrate", return_value=True))
                query = stack.enter_context(patch.object(model._base_manager, "using"))
                query.return_value.order_by.return_value._prefetch_related_lookups = ()
                query.return_value.order_by.return_value.iterator.return_value = iter([obj])
            # Keep the original characterization against the unmodified Django path.
            from django.db.backends.base.creation import BaseDatabaseCreation
            serialized = BaseDatabaseCreation.serialize_db_to_string(creation)
        return serialized, creation, conn, app, ordered

    def test_real_django_serialization_and_restore_preserve_problematic_order(self):
        """Characterization, NOT a PostgreSQL trigger execution or a backend fix."""
        import json
        from contextlib import nullcontext
        from django.core.serializers.base import DeserializedObject
        serialized, creation, conn, app, ordered = self.serialization_probe()
        rows = json.loads(serialized)
        self.assertEqual([row["model"] for row in rows],
                         ["people.person", "people.identificationkind"])
        self.assertEqual(rows[0]["fields"]["identification_kind"], rows[1]["pk"])
        # Run the actual Django restore iterator. Replace only transaction/DB
        # writes; record the order the real deserializer requests INSERT/save.
        seen = []
        with patch("django.db.backends.base.creation.atomic", return_value=nullcontext()), \
             patch.object(DeserializedObject, "save", autospec=True,
                          side_effect=lambda obj: seen.append(obj.object._meta.label_lower)):
            PostgreSQLCreation.deserialize_db_from_string(creation, serialized)
        self.assertEqual(seen, ["people.person", "people.identificationkind"])
        conn.check_constraints.assert_called_once_with(table_names={
            "people_person", "people_identificationkind"})
        self.driver.assert_not_called()
        self.network.assert_not_called()

    def test_django_natural_key_sort_does_not_order_plain_fk_catalog(self):
        from django.core import serializers
        serialized, creation, conn, app, ordered = self.serialization_probe()
        self.assertFalse(hasattr(ordered[0], "natural_key"))
        self.assertFalse(hasattr(ordered[1], "natural_key"))
        self.assertEqual(serializers.sort_dependencies([(app, ordered)]), ordered)
        self.driver.assert_not_called()


    def test_reordered_real_snapshot_restores_catalog_before_person(self):
        import json
        from contextlib import nullcontext
        from django.core.serializers.base import DeserializedObject
        from django.db.backends.postgresql.creation import DatabaseCreation as PostgreSQLCreation
        snapshot, creation, conn, app, ordered = self.serialization_probe()
        with patch.object(PostgreSQLCreation, "serialize_db_to_string", return_value=snapshot) as parent:
            corrected = creation.serialize_db_to_string()
        parent.assert_called_once_with()
        original_rows, corrected_rows = json.loads(snapshot), json.loads(corrected)
        self.assertEqual(corrected_rows, [original_rows[1], original_rows[0]])
        self.assertEqual([r["model"] for r in corrected_rows],
                         ["people.identificationkind", "people.person"])
        seen = []
        with patch("django.db.backends.base.creation.atomic", return_value=nullcontext()), \
             patch.object(DeserializedObject, "save", autospec=True,
                          side_effect=lambda obj: seen.append(obj.object._meta.label_lower)):
            PostgreSQLCreation.deserialize_db_from_string(creation, corrected)
        self.assertEqual(seen, ["people.identificationkind", "people.person"])
        self.driver.assert_not_called(); conn.cursor.assert_not_called()

    def test_reordering_preserves_records_pk_types_values_and_other_order(self):
        import json
        rows = [
            {"model": "auth.user", "pk": "u1", "fields": {"active": True, "nullable": None}},
            {"model": "people.person", "pk": 9007199254740993,
             "fields": {"identification_kind": 11, "text": "á\n\\", "decimal": "0.00"}},
            {"model": "core.company", "pk": 3, "fields": {"data": {"x": [1, 1.5, False, None]}}},
            {"model": "people.identificationkind", "pk": 11, "fields": {"code": "OTHER"}},
            {"model": "people.person", "pk": 2, "fields": {"identification_kind": 12}},
            {"model": "people.identificationkind", "pk": 12, "fields": {"code": "PASSPORT"}},
        ]
        result = json.loads(DatabaseCreation._order_identification_catalog(json.dumps(rows)))
        self.assertEqual(result, [rows[i] for i in [0, 3, 5, 1, 2, 4]])
        self.assertEqual(len(result), len(rows))
        self.assertEqual([r for r in result if r["model"] != "people.identificationkind"],
                         [r for r in rows if r["model"] != "people.identificationkind"])
        for row in rows:
            restored = next(r for r in result if (r["model"], r["pk"]) == (row["model"], row["pk"]))
            self.assertEqual(restored, row)
            self.assertIs(type(restored["pk"]), type(row["pk"]))
        self.assertIs(type(result[3]["fields"]["identification_kind"]), int)
        self.assertIs(type(result[4]["fields"]["data"]["x"][1]), float)
        self.driver.assert_not_called()

    def test_empty_snapshot_remains_exactly_unchanged(self):
        for snapshot in ["[]", "[  ]\n"]:
            self.assertEqual(DatabaseCreation._order_identification_catalog(snapshot), snapshot)

    def test_missing_person_or_catalog_preserves_exact_snapshot(self):
        import json
        for models in [["core.company", "people.person"],
                       ["core.company", "people.identificationkind"],
                       ["core.company", "auth.user"]]:
            snapshot = json.dumps([{"model": m, "pk": i, "fields": {}}
                                   for i, m in enumerate(models)], indent=2)
            self.assertEqual(DatabaseCreation._order_identification_catalog(snapshot), snapshot)

    def test_already_valid_snapshot_unchanged_and_ordering_idempotent(self):
        snapshot, creation, conn, app, ordered = self.serialization_probe()
        corrected = creation._order_identification_catalog(snapshot)
        self.assertEqual(creation._order_identification_catalog(corrected), corrected)

    def test_unexpected_snapshot_formats_rejected_without_contents_in_error(self):
        import json
        invalid = [None, b"[]", "", "not-json", "{}", "null", "[null]", "[[]]",
                   '[{"model":"people.person","pk":1}]',
                   '[{"model":"people.person","pk":1,"fields":[],"extra":1}]',
                   '[{"model":"people.person","pk":{},"fields":{}}]',
                   '[{"model":"people.person","pk":1,"fields":{"x":NaN}}]',
                   '[{"model":"people.person","pk":1,"fields":{"x":1e999}}]',
                   '[{"model":"people.person","pk":1,"pk":2,"fields":{}}]',
                   '[{"model":"people.person","pk":1,"fields":{"x":1,"x":2}}]']
        for snapshot in invalid:
            with self.subTest(snapshot=snapshot), self.assertRaises(ImproperlyConfigured) as caught:
                DatabaseCreation._order_identification_catalog(snapshot)
            self.assertEqual(str(caught.exception),
                             "R-01 Base rejected an unexpected Django snapshot format.")
        self.driver.assert_not_called()

    def test_restore_override_delegates_to_standard_django(self):
        source = __import__("inspect").getsource(DatabaseCreation.deserialize_db_from_string)
        self.assertIn("super().deserialize_db_from_string", source)
        self.assertIsNot(DatabaseCreation.deserialize_db_from_string,
                         PostgreSQLCreation.deserialize_db_from_string)


    def exact_snapshot(self):
        from datetime import datetime, timezone
        from core.testing.r01_base_json import Serializer
        self.serialization_probe()  # Existing setup path; reads/network remain blocked.
        from people.models import IdentificationKind, Person
        from people.identification import FINAL_CONSUMER_ID
        dates = dict(created_at=datetime(2026, 1, 2, 3, 4, 5, 123456, timezone.utc),
                     updated_at=datetime(2026, 1, 2, 3, 4, 5, 123001, timezone.utc))
        kind = IdentificationKind(pk=202, code="FINAL_CONSUMER", name="Consumidor Final", **dates)
        other = IdentificationKind(pk=203, code="OTHER", name="Otro", **dates)
        person = Person(pk=101, identification=FINAL_CONSUMER_ID,
                        identification_type="FINAL_CONSUMER", identification_kind_id=kind.pk,
                        person_type="NATURAL", full_name="CONSUMIDOR FINAL", **dates)
        return Serializer().serialize([person, other, kind]), [person, other, kind]

    def restore_harness(self, snapshot, stored, *, fail_save=False, corrupt_save=False):
        """Run actual validation, comparison, filtering and Django deserialization.

        Replace only persistence and transaction contexts with an in-memory adapter.
        This demonstrates atomic boundary/exception wiring, not PostgreSQL rollback.
        """
        import copy
        from contextlib import contextmanager, ExitStack
        from django.core.serializers.base import DeserializedObject
        from people.models import Person, IdentificationKind
        creation, conn = self.creation()
        conn._test_serialized_contents = snapshot
        state = {(type(obj), obj.pk): copy.deepcopy(obj) for obj in stored}
        original = copy.deepcopy(state)
        writes = []
        events = []

        @contextmanager
        def atomic(*, using):
            self.assertEqual(using, "default")
            before = copy.deepcopy(state)
            events.append("enter")
            try:
                yield
            except Exception:
                state.clear(); state.update(before)
                events.append("rollback")
                raise
            else:
                events.append("commit")

        def save(obj, **kwargs):
            value = copy.deepcopy(obj.object)
            writes.append((type(value), value.pk))
            state[type(value), value.pk] = value
            if corrupt_save:
                value.name = "corrupt"
            if fail_save:
                raise RuntimeError("synthetic restore failure")

        with ExitStack() as stack:
            stack.enter_context(patch("core.testing.r01_base_postgresql.creation.settings", self.settings()))
            stack.enter_context(patch("core.testing.r01_base_postgresql.creation.transaction.atomic", atomic))
            stack.enter_context(patch("django.db.backends.base.creation.atomic", atomic))
            saver = stack.enter_context(patch.object(DeserializedObject, "save", autospec=True, side_effect=save))
            managers = []
            for model in (Person, IdentificationKind):
                query = MagicMock()
                protected = [obj for obj in state.values() if type(obj) is model and (
                    model is Person or obj.code == "FINAL_CONSUMER")]
                query.select_for_update.return_value.filter.return_value = protected
                query.get.side_effect = lambda *, pk, model=model: state[model, pk]
                managers.append(stack.enter_context(patch.object(model._base_manager, "using", return_value=query)))
            try:
                creation.deserialize_db_from_string(snapshot)
                error = None
            except Exception as caught:
                error = caught
        return SimpleNamespace(error=error, state=state, original=original, writes=writes,
                               events=events, saver=saver, managers=managers, conn=conn)

    def test_exact_encoder_datetime_time_and_standard_field_deserialization(self):
        import json
        from datetime import datetime, time, timezone
        from django.db import models
        from core.testing.r01_base_json import ExactTemporalEncoder, Deserializer
        for micros in (123456, 123001, 0):
            dt = datetime(2026, 1, 2, 3, 4, 5, micros, timezone.utc)
            tm = time(3, 4, 5, micros)
            values = json.loads(json.dumps([dt, tm], cls=ExactTemporalEncoder))
            self.assertEqual(models.DateTimeField().to_python(values[0]), dt)
            self.assertEqual(models.TimeField().to_python(values[1]), tm)
            self.assertIn(f".{micros:06d}", values[0])
            self.assertIn(f".{micros:06d}", values[1])
        snapshot, objects = self.exact_snapshot()
        restored = [obj.object for obj in Deserializer(snapshot, using="default")]
        self.assertEqual([obj.created_at for obj in restored], [obj.created_at for obj in objects])
        self.assertEqual([obj.updated_at for obj in restored], [obj.updated_at for obj in objects])

    def test_exact_serializer_is_registered_only_in_base_settings(self):
        snapshot, objects = self.exact_snapshot()
        from django.core import serializers
        from django.conf import settings
        from core.testing.r01_base_json import Serializer, Deserializer
        self.assertEqual(settings.SERIALIZATION_MODULES, {"json": "core.testing.r01_base_json"})
        self.assertIs(serializers.get_serializer("json"), Serializer)
        self.assertIs(serializers.get_deserializer("json"), Deserializer)
        self.assertIn(".123456", serializers.serialize("json", objects))

    def test_identical_reserved_row_is_never_saved_and_snapshot_unchanged(self):
        snapshot, objects = self.exact_snapshot()
        original = snapshot
        result = self.restore_harness(snapshot, objects)
        self.assertIsNone(result.error)
        self.assertNotIn((type(objects[0]), objects[0].pk), result.writes)
        self.assertEqual(len(result.writes), 2)
        self.assertEqual(snapshot, original)
        self.assertEqual(result.conn._test_serialized_contents, original)
        for key, obj in result.original.items():
            self.assertFalse(DatabaseCreation._different_fields(obj, result.state[key]))
        for manager in result.managers:
            self.assertEqual(manager.call_args.args, ("default",))
            manager.return_value.select_for_update.assert_called_once_with()
        self.driver.assert_not_called(); self.network.assert_not_called()

    def test_one_microsecond_difference_rejected_before_any_write(self):
        from datetime import timedelta
        snapshot, objects = self.exact_snapshot()
        objects[0].created_at += timedelta(microseconds=1)
        result = self.restore_harness(snapshot, objects)
        self.assertIsInstance(result.error, ImproperlyConfigured)
        self.assertIn("created_at", str(result.error))
        result.saver.assert_not_called()
        self.assertIn("rollback", result.events)

    def test_all_reserved_fields_are_compared_without_values_in_errors(self):
        for field, value in (("full_name", "private-value"), ("identification_kind_id", 203),
                             ("is_active", False), ("updated_at", None)):
            with self.subTest(field=field):
                snapshot, objects = self.exact_snapshot()
                setattr(objects[0], field, value)
                result = self.restore_harness(snapshot, objects)
                self.assertIsInstance(result.error, ImproperlyConfigured)
                self.assertNotIn("private-value", str(result.error))
                result.saver.assert_not_called()

    def test_reserved_pk_identity_and_catalog_conflicts_rejected_before_save(self):
        for conflict in ("pk", "identity", "crossed", "kind_pk", "kind_code", "missing_kind"):
            with self.subTest(conflict=conflict):
                snapshot, objects = self.exact_snapshot()
                if conflict == "pk": objects[0].pk += 1
                if conflict == "identity": objects[0].identification = "OTHER-IDENTITY"
                if conflict == "crossed":
                    import copy
                    extra = copy.deepcopy(objects[0]); extra.pk += 1; objects.append(extra)
                if conflict == "kind_pk": objects[2].pk += 1
                if conflict == "kind_code": objects[2].code = "OTHER"
                if conflict == "missing_kind": objects = objects[:2]
                result = self.restore_harness(snapshot, objects)
                self.assertIsInstance(result.error, ImproperlyConfigured)
                result.saver.assert_not_called()

    def test_absent_reserved_uses_standard_restore_and_preserves_order_and_records(self):
        snapshot, objects = self.exact_snapshot()
        result = self.restore_harness(snapshot, [])
        self.assertIsNone(result.error)
        self.assertEqual(result.writes, [(type(objects[i]), objects[i].pk) for i in (1, 2, 0)])
        self.assertEqual(len(result.state), len(objects))
        for obj in objects:
            self.assertFalse(DatabaseCreation._different_fields(obj, result.state[type(obj), obj.pk]))
        result.conn.check_constraints.assert_called_with(table_names={
            "people_person", "people_identificationkind"})

    def test_malformed_or_incomplete_snapshot_rejected_before_persistence(self):
        import json
        for defect in ("missing_field", "unknown_field", "duplicate_pk", "truncated_time",
                       "bad_fk", "missing_reserved", "wrong_reserved_kind", "noncanonical_model",
                       "invalid_string", "invalid_boolean", "invalid_integer_pk"):
            with self.subTest(defect=defect):
                snapshot, objects = self.exact_snapshot()
                rows = json.loads(snapshot)
                if defect == "missing_field": del rows[0]["fields"]["full_name"]
                if defect == "unknown_field": rows[0]["fields"]["unknown"] = "x"
                if defect == "duplicate_pk": rows.append(rows[0])
                if defect == "truncated_time": rows[0]["fields"]["created_at"] = "2026-01-02T03:04:05.123+00:00"
                if defect == "bad_fk": rows[0]["fields"]["identification_kind"] = 999
                if defect == "noncanonical_model": rows[0]["model"] = "people.Person"
                if defect == "invalid_string": rows[0]["fields"]["full_name"] = {"bad": "value"}
                if defect == "invalid_boolean": rows[0]["fields"]["is_active"] = 1
                if defect == "invalid_integer_pk": rows[0]["pk"] = True
                if defect == "missing_reserved": rows.pop(0)
                if defect == "wrong_reserved_kind": rows[2]["fields"]["code"] = "OTHER"
                result = self.restore_harness(json.dumps(rows), objects)
                self.assertIsInstance(result.error, ImproperlyConfigured)
                result.saver.assert_not_called()
                for manager in result.managers: manager.assert_not_called()

    def test_restore_failure_rolls_back_entire_atomic_boundary(self):
        snapshot, objects = self.exact_snapshot()
        result = self.restore_harness(snapshot, [], fail_save=True)
        self.assertIsInstance(result.error, RuntimeError)
        self.assertTrue(result.writes)
        self.assertFalse(result.state)
        self.assertEqual(result.events.count("rollback"), 2)

    def test_final_equivalence_failure_rolls_back_all_restored_records(self):
        snapshot, objects = self.exact_snapshot()
        result = self.restore_harness(snapshot, [], corrupt_save=True)
        self.assertIsInstance(result.error, ImproperlyConfigured)
        self.assertTrue(result.writes)
        self.assertFalse(result.state)
        self.assertEqual(result.events[-1], "rollback")


    def test_exact_time_encoder_rejects_aware_time(self):
        import json
        from datetime import time, timezone
        from core.testing.r01_base_json import ExactTemporalEncoder
        with self.assertRaises(ValueError):
            json.dumps(time(3, 4, 5, 123456, timezone.utc), cls=ExactTemporalEncoder)

    def test_validated_snapshot_does_not_read_database(self):
        from core.testing.r01_base_json import Deserializer
        snapshot, expected = self.exact_snapshot()
        rows, typed = DatabaseCreation._typed_snapshot(snapshot)
        self.assertEqual([obj.object.pk for obj in typed], [203, 202, 101])
        self.assertEqual([obj.object.created_at.microsecond for obj in typed], [123456] * 3)
        self.assertEqual([obj.object.updated_at.microsecond for obj in typed], [123001] * 3)
        self.assertEqual(len(list(Deserializer(snapshot, using="default"))), len(rows))
        self.driver.assert_not_called(); self.network.assert_not_called()


    def test_real_parent_serialization_uses_exact_encoder_and_catalog_order(self):
        from contextlib import ExitStack
        from people.models import Person, IdentificationKind
        snapshot, objects = self.exact_snapshot()
        creation, conn = self.creation()
        app = SimpleNamespace(models_module=object(), label="people", name="people",
                              get_models=lambda: iter((Person, IdentificationKind)))
        with ExitStack() as stack:
            stack.enter_context(patch("django.db.backends.base.creation.apps.get_app_configs", return_value=[app]))
            stack.enter_context(patch("django.db.migrations.loader.MigrationLoader",
                                      return_value=SimpleNamespace(migrated_apps={"people"})))
            stack.enter_context(patch("django.db.backends.base.creation.router.allow_migrate_model", return_value=True))
            for model in (Person, IdentificationKind):
                stack.enter_context(patch.object(model._meta, "can_migrate", return_value=True))
                query = stack.enter_context(patch.object(model._base_manager, "using"))
                query.return_value.order_by.return_value._prefetch_related_lookups = ()
                query.return_value.order_by.return_value.iterator.return_value = iter(
                    [obj for obj in objects if type(obj) is model])
            serialized = creation.serialize_db_to_string()
        rows, typed = DatabaseCreation._typed_snapshot(serialized)
        self.assertEqual([row["model"] for row in rows],
                         ["people.identificationkind", "people.identificationkind", "people.person"])
        self.assertTrue(all(obj.object.created_at.microsecond == 123456 for obj in typed))
        self.assertTrue(all(obj.object.updated_at.microsecond == 123001 for obj in typed))
        self.driver.assert_not_called(); self.network.assert_not_called()

    def test_restore_requires_execution_gate_before_reads_or_writes(self):
        snapshot, objects = self.exact_snapshot()
        with patch.dict(os.environ, {}, clear=True):
            result = self.restore_harness(snapshot, objects)
        self.assertIsInstance(result.error, ImproperlyConfigured)
        result.saver.assert_not_called()
        for manager in result.managers:
            manager.assert_not_called()
