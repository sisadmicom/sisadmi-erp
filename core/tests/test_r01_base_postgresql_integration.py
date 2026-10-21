"""Opt-in PostgreSQL integration; standard teardown flushes only R-01 Base.

Run only after separate execution approval, with the R-01 Base settings/runner,
--keepdb and --parallel=1. Failfast does not suppress Django teardown.
No fixtures, business data, trigger changes or automatic repairs are performed.
"""
from contextlib import contextmanager
from importlib import import_module
import json
import sys

from django.conf import settings
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from core.testing import r01_base_guard as guard
from people.identification import FINAL_CONSUMER_ID
from people.models import IdentificationKind, Person


_CONSTRAINTS = {
    "people_person_identity_coherent",
    "people_person_identity_immutable",
    "people_person_reserved_protected",
    "people_identification_kind_code_immutable",
}


def _sql_diagnostic(error):
    cause = error.__cause__
    state = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
    if not isinstance(state, str) or len(state) != 5 or not state.isalnum():
        state = "unavailable"
    constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
    return state, constraint if constraint in _CONSTRAINTS else "unavailable"


@contextmanager
def _diagnostics(phase):
    """Emit safe evidence before standard teardown, never server error text/data."""
    try:
        yield
    except Exception as error:
        state, constraint = _sql_diagnostic(error)
        detail = f"R01 integration failure: phase={phase}; SQLSTATE={state}; constraint={constraint}"
        print(detail, file=sys.stderr, flush=True)
        raise AssertionError(detail) from None


class R01BasePostgreSQLIntegrationTests(TransactionTestCase):
    databases = {"default"}
    serialized_rollback = True

    @classmethod
    def _fixture_setup(cls):
        # Preserve Django's actual restore, including its first-test restore.
        with _diagnostics("serialized_restore"):
            guard.validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
            guard.require_execution()
            super()._fixture_setup()

    def _fixture_teardown(self):
        # Preserve standard internal flush; this is not a manual cleanup path.
        with _diagnostics("standard_teardown"):
            super()._fixture_teardown()

    def _assert_identity_and_migrations(self):
        connection = connections["default"]
        self.assertEqual(settings.TEST_RUNNER, "core.testing.r01_base_runner.R01BaseTestRunner")
        guard.validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
        guard.require_execution()
        with connection.cursor() as cursor:
            guard.verify_identity(cursor)  # Includes owner, privileges and memberships.
            cursor.execute("SHOW session_replication_role")
            self.assertEqual(cursor.fetchone(), ("origin",))
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        self.assertIn(
            ("people", "0011_person_identity_immutable"),
            executor.loader.applied_migrations,
        )
        self.assertFalse(executor.migration_plan(executor.loader.graph.leaf_nodes()))

    def _assert_trigger_objects(self):
        expected = {
            "people_person_identity_immutable":
                ("people_person", "sisadmi_person_identity_guard", 27),
            "people_person_identity_coherent":
                ("people_person", "sisadmi_person_identity_insert_guard", 7),
            "people_identification_kind_code_immutable":
                ("people_identificationkind", "sisadmi_identification_kind_code_guard", 19),
        }
        # tgtype bits: ROW=1, BEFORE=2, INSERT=4, DELETE=8, UPDATE=16.
        with connections["default"].cursor() as cursor:
            cursor.execute(
                "SELECT t.tgname,c.relname,p.proname,t.tgtype,t.tgenabled,"
                "pn.nspname,p.pronargs,p.prorettype='pg_catalog.trigger'::regtype,l.lanname "
                "FROM pg_catalog.pg_trigger t "
                "JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                "JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid "
                "JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace "
                "JOIN pg_catalog.pg_language l ON l.oid=p.prolang "
                "WHERE n.nspname='public' AND NOT t.tgisinternal AND t.tgname IN (%s,%s,%s)",
                list(expected),
            )
            rows = cursor.fetchall()
        self.assertEqual(len(rows), len(expected))
        self.assertEqual({row[0] for row in rows}, set(expected))
        for name, table, function, bits, enabled, schema, nargs, returns_trigger, language in rows:
            self.assertEqual((table, function, bits), expected[name])
            self.assertEqual((enabled, schema, nargs, returns_trigger, language),
                             ("O", "public", 0, True, "plpgsql"))

    def _assert_restored_reference_data(self):
        kinds = import_module(
            "people.migrations.0010_identification_catalog_and_final_consumer"
        ).KINDS
        self.assertEqual(
            set(IdentificationKind.objects.using("default").values_list("code", "name")),
            set(kinds),
        )
        self.assertEqual(IdentificationKind.objects.using("default").count(), len(kinds))
        self.assertFalse(IdentificationKind.objects.using("default").filter(is_active=False).exists())
        people = Person.objects.using("default")
        self.assertEqual(people.count(), 1)  # Fresh migrated base; never adopt business data.
        person = people.get(identification=FINAL_CONSUMER_ID)
        self.assertEqual(person.full_name, "CONSUMIDOR FINAL")
        self.assertEqual(person.person_type, "NATURAL")
        self.assertEqual(person.identification_type, "FINAL_CONSUMER")
        self.assertTrue(person.is_active)
        self.assertEqual(person.identification_kind_id,
                         IdentificationKind.objects.using("default").get(code="FINAL_CONSUMER").pk)

        snapshot = getattr(connections["default"], "_test_serialized_contents", None)
        self.assertIsInstance(snapshot, str)
        initial = json.loads(snapshot)
        models = (IdentificationKind, Person)
        labels = {model._meta.label_lower for model in models}
        expected = [row for row in initial if row["model"] in labels]
        # Decode exact timestamps to typed values; never compare rounded JSON.
        from core.testing.r01_base_postgresql.creation import DatabaseCreation
        _, typed = DatabaseCreation._typed_snapshot(snapshot)
        reference = [item.object for item in typed if item.object._meta.label_lower in labels]
        self.assertEqual(len(expected), len(kinds) + 1)
        for obj in reference:
            actual = type(obj)._base_manager.using("default").get(pk=obj.pk)
            self.assertFalse(DatabaseCreation._different_fields(obj, actual),
                             "Restored reference record differs from the exact snapshot")
        return person

    def _assert_sql_rejected(self, label, sql, params, constraint):
        error = None
        try:
            with transaction.atomic(using="default"):
                with connections["default"].cursor() as cursor:
                    cursor.execute(sql, params)
                # Even if a trigger is absent, never commit a successful probe.
                transaction.set_rollback(True, using="default")
        except DatabaseError as caught:
            error = caught
        if error is None:
            self.fail(f"Trigger probe unexpectedly accepted: {label}")
        state, actual_constraint = _sql_diagnostic(error)
        print(f"R01 trigger probe: {label}; SQLSTATE={state}; constraint={actual_constraint}",
              file=sys.stderr, flush=True)
        self.assertIsInstance(error, IntegrityError)
        self.assertEqual((state, actual_constraint), ("23514", constraint))

    def _assert_trigger_rejections(self, person):
        kinds = dict(IdentificationKind.objects.using("default").values_list("code", "pk"))
        insert = (
            "INSERT INTO public.people_person "
            "(created_at,updated_at,is_active,identification,identification_type,"
            "identification_kind_id,person_type,full_name,phone,address) "
            "VALUES (CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,true,%s,%s,%s,'NATURAL',%s,'','')"
        )
        # Synthetic identifiers are used only in deliberately rejected SQL inserts.
        for label, identification_type, kind in (
            ("mismatched_catalog", "CEDULA", kinds["PASSPORT"]),
            ("null_classification", None, None),
            ("reserved_classification", "FINAL_CONSUMER", kinds["FINAL_CONSUMER"]),
        ):
            identifier = "R01-TRIGGER-PROBE"
            self._assert_sql_rejected(label, insert,
                                      [identifier, identification_type, kind, "Rejected probe"],
                                      "people_person_identity_coherent")
            self.assertFalse(Person.objects.using("default").filter(identification=identifier).exists())
        for label, sql, params, constraint in (
            ("immutable_identity", "UPDATE public.people_person SET identification_type=%s WHERE id=%s",
             ["OTHER", person.pk], "people_person_identity_immutable"),
            ("reserved_update", "UPDATE public.people_person SET full_name=%s WHERE id=%s",
             ["Rejected probe", person.pk], "people_person_reserved_protected"),
            ("reserved_delete", "DELETE FROM public.people_person WHERE id=%s",
             [person.pk], "people_person_reserved_protected"),
            ("immutable_catalog", "UPDATE public.people_identificationkind SET code=%s WHERE id=%s",
             ["R01_REJECTED", kinds["CEDULA"]], "people_identification_kind_code_immutable"),
        ):
            self._assert_sql_rejected(label, sql, params, constraint)

    def _assert_integration_contract(self):
        for phase, check in (
            ("identity_migrations", self._assert_identity_and_migrations),
            ("trigger_objects", self._assert_trigger_objects),
            ("restored_reference_data", self._assert_restored_reference_data),
        ):
            with _diagnostics(phase):
                result = check()
        with _diagnostics("trigger_rejections"):
            self._assert_trigger_rejections(result)
        with _diagnostics("reference_data_after_probes"):
            self._assert_restored_reference_data()

    def test_first_restore_and_trigger_contract(self):
        self._assert_integration_contract()

    def test_repeated_restore_and_trigger_contract(self):
        self._assert_integration_contract()
