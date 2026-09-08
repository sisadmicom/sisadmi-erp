from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase


class LineBehaviorMigrationTest(TransactionTestCase):
    before = [("core", "0006_remove_sequence_legacy_identity")]
    target = [("core", "0007_document_type_line_behavior")]
    expected = {
        "SALES_INVOICE": "COMMERCIAL",
        "PURCHASE_INVOICE": "COMMERCIAL",
        "INVENTORY_TRANSFER": "QUANTITY",
    }

    def setUp(self):
        executor = MigrationExecutor(connection)
        self.latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        self.model = executor.loader.project_state(self.before).apps.get_model("core", "DocumentType")
        self.addCleanup(self.restore_schema)
        for code in self.expected:
            self.model.objects.update_or_create(
                code=code, defaults={"name": code, "category": "SALES", "requires_detail": True},
            )

    def restore_schema(self):
        self.model.objects.filter(code__in=["UNKNOWN_A", "UNKNOWN_B"]).delete()
        MigrationExecutor(connection).migrate(self.latest)

    def migrate_forward(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.target)
        return executor.loader.project_state(self.target).apps.get_model("core", "DocumentType")

    def test_unknown_types_abort_without_silent_classification_or_data_changes(self):
        for code in ("UNKNOWN_A", "UNKNOWN_B"):
            self.model.objects.create(code=code, name=code, category="SALES", requires_detail=False)
        original = list(self.model.objects.order_by("code").values())
        with self.assertRaisesRegex(RuntimeError, "sin clasificación explícita") as error:
            self.migrate_forward()
        self.assertIn("UNKNOWN_A", str(error.exception))
        self.assertIn("UNKNOWN_B", str(error.exception))
        self.assertEqual(list(self.model.objects.order_by("code").values()), original)
        self.assertNotIn(self.target[0], MigrationRecorder(connection).applied_migrations())
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(cursor, "core_documenttype")
        self.assertNotIn("line_behavior", {column.name for column in columns})

    def test_classification_preserves_existing_fields_and_rollback_removes_only_new_field(self):
        original = list(self.model.objects.order_by("code").values())
        model = self.migrate_forward()
        self.assertFalse(model._meta.get_field("line_behavior").null)
        self.assertEqual(model._meta.get_field("line_behavior").default, "NONE")
        after = list(model.objects.order_by("code").values())
        for row in after:
            self.assertEqual(row.pop("line_behavior"), self.expected[row["code"]])
        self.assertEqual(after, original)
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(cursor, "core_documenttype")
            constraints = connection.introspection.get_constraints(cursor, "core_documenttype")
        self.assertFalse(next(column for column in columns if column.name == "line_behavior").null_ok)
        self.assertTrue(constraints["document_type_line_behavior_consistent"]["check"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.filter(code="SALES_INVOICE").update(line_behavior=None)
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.filter(code="SALES_INVOICE").update(line_behavior="NONE")

        # A later explicit classification is not replaced with an invented one
        # during rollback; the added column is simply removed.
        model.objects.filter(code="SALES_INVOICE").update(line_behavior="VALUED")
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        historical = executor.loader.project_state(self.before).apps.get_model("core", "DocumentType")
        self.assertNotIn("line_behavior", {field.name for field in historical._meta.fields})
        self.assertEqual(list(historical.objects.order_by("code").values()), original)
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(cursor, "core_documenttype")
        self.assertNotIn("line_behavior", {column.name for column in columns})
