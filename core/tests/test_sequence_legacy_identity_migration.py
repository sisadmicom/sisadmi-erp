from django.db import connection, IntegrityError, transaction
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase


class SequenceLegacyIdentityMigrationTest(TransactionTestCase):
    before = [("core", "0005_sequence_document_type")]
    target = [("core", "0006_remove_sequence_legacy_identity")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        self.latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        self.apps = executor.loader.project_state(self.before).apps
        self.Sequence = self.apps.get_model("core", "Sequence")
        self.addCleanup(self.restore_schema)
        self.document_types = []
        for code, category in (("SALES_INVOICE", "SALES"), ("PURCHASE_INVOICE", "PURCHASES")):
            document_type, _ = self.apps.get_model("core", "DocumentType").objects.get_or_create(
                code=code, defaults={"name": code, "category": category},
            )
            self.document_types.append(document_type)
        person = self.apps.get_model("people", "Person").objects.create(
            identification="1790000001001", person_type="LEGAL", full_name="Empresa",
        )
        self.company = self.apps.get_model("core", "Company").objects.create(person=person)
        self.branch = self.apps.get_model("core", "Branch").objects.create(
            company=self.company, code="001", name="Matriz",
        )

    def restore_schema(self):
        self.Sequence.objects.all().delete()
        MigrationExecutor(connection).migrate(self.latest)

    def create_sequence(self, code, document_type=None, is_active=True):
        return self.Sequence.objects.create(
            company=self.company, branch=self.branch, code=code,
            document_type=document_type, name=f"Administrativa {code}",
            next_number=87, prefix="ERP-", series="009", padding=8, is_active=is_active,
        )

    def migrate_forward(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.target)
        return executor.loader.project_state(self.target).apps.get_model("core", "Sequence")

    def test_unclassified_sequences_block_transition_until_explicitly_classified(self):
        pending = self.create_sequence("HISTORICAL", is_active=False)
        classified = self.create_sequence("SAL", self.document_types[0])
        original = {row["id"]: row for row in self.Sequence.objects.values()}
        with self.assertRaisesRegex(RuntimeError, "históricas pendientes de clasificación") as error:
            self.migrate_forward()
        self.assertIn(str(pending.pk), str(error.exception))
        self.assertNotIn(self.target[0], MigrationRecorder(connection).applied_migrations())
        self.assertEqual({row["id"]: row for row in self.Sequence.objects.values()}, original)
        with connection.cursor() as cursor:
            columns = {c.name: c for c in connection.introspection.get_table_description(cursor, "core_sequence")}
            constraints = connection.introspection.get_constraints(cursor, "core_sequence")
        self.assertIn("code", columns)
        self.assertTrue(columns["document_type_id"].null_ok)
        self.assertIn("unique_sequence_company_branch_code", constraints)

        # Classification is an explicit administrative action, outside migration.
        self.Sequence.objects.filter(pk=pending.pk).update(document_type=self.document_types[1])
        original[pending.pk]["document_type_id"] = self.document_types[1].pk
        model = self.migrate_forward()
        self.assertNotIn("code", {field.name for field in model._meta.fields})
        self.assertFalse(model._meta.get_field("document_type").null)
        for row in model.objects.values():
            expected = original[row["id"]].copy()
            expected.pop("code")
            self.assertEqual(row, expected)
        self.assertEqual(model.objects.count(), 2)
        with connection.cursor() as cursor:
            columns = {c.name: c for c in connection.introspection.get_table_description(cursor, "core_sequence")}
            constraints = connection.introspection.get_constraints(cursor, "core_sequence")
        self.assertNotIn("code", columns)
        self.assertFalse(columns["document_type_id"].null_ok)
        self.assertNotIn("unique_sequence_company_branch_code", constraints)
        self.assertTrue(constraints["unique_sequence_company_branch_document_type"]["unique"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.filter(pk=classified.pk).update(document_type_id=None)
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.create(
                company_id=self.company.pk, branch_id=self.branch.pk,
                document_type_id=self.document_types[0].pk, name="Duplicada", prefix="DUP-",
            )

    def test_rollback_rejects_data_and_is_safe_when_empty(self):
        self.create_sequence("CUSTOM", self.document_types[0])
        model = self.migrate_forward()
        original = list(model.objects.values())
        with self.assertRaisesRegex(IrreversibleError, "códigos históricos no pueden reconstruirse"):
            MigrationExecutor(connection).migrate(self.before)
        self.assertEqual(list(model.objects.values()), original)
        self.assertIn(self.target[0], MigrationRecorder(connection).applied_migrations())
        with connection.cursor() as cursor:
            columns = {c.name: c for c in connection.introspection.get_table_description(cursor, "core_sequence")}
        self.assertNotIn("code", columns)
        self.assertFalse(columns["document_type_id"].null_ok)

        model.objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        model = executor.loader.project_state(self.before).apps.get_model("core", "Sequence")
        self.assertIn("code", {field.name for field in model._meta.fields})
        self.assertTrue(model._meta.get_field("document_type").null)
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, "core_sequence")
        self.assertIn("unique_sequence_company_branch_code", constraints)
        self.assertIn("unique_sequence_company_branch_document_type", constraints)
        self.assertFalse(model.objects.exists())
