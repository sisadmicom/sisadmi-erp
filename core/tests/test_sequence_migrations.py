from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SequenceMigrationTest(TransactionTestCase):
    def test_backfill_and_rollback_preserve_historical_sequences(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [("core", "0004_seed_document_types")]
        target = [("core", "0005_sequence_document_type")]
        expected = {
            "SAL": "SALES_INVOICE",
            "PUR": "PURCHASE_INVOICE",
            "TRF": "INVENTORY_TRANSFER",
            "UNKNOWN": None,
            "TEST": None,
        }
        try:
            apps = executor.loader.project_state(latest).apps
            document_types = {}
            for code, category in (
                ("SALES_INVOICE", "SALES"),
                ("PURCHASE_INVOICE", "PURCHASES"),
                ("INVENTORY_TRANSFER", "INVENTORY"),
            ):
                document_types[code], _ = apps.get_model("core", "DocumentType").objects.get_or_create(
                    code=code, defaults={"name": code, "category": category},
                )
            executor.migrate(before)
            apps = executor.loader.project_state(before).apps
            person = apps.get_model("people", "Person").objects.create(
                identification="1790000001001", person_type="LEGAL", full_name="Empresa",
            )
            company = apps.get_model("core", "Company").objects.create(person=person)
            branch = apps.get_model("core", "Branch").objects.create(
                company=company, code="001", name="Matriz",
            )
            model = apps.get_model("core", "Sequence")
            original = {}
            for index, code in enumerate(expected):
                sequence = model.objects.create(
                    company=company, branch=branch, code=code, name=f"Histórica {code}",
                    prefix="OLD-", series="009", padding=8, next_number=35 + index,
                    is_active=code != "PUR",
                )
                original[sequence.pk] = model.objects.values().get(pk=sequence.pk)

            executor = MigrationExecutor(connection)
            executor.migrate(target)
            state = executor.loader.project_state(target)
            model = state.apps.get_model("core", "Sequence")
            self.assertEqual(model.objects.count(), len(expected))
            for pk, values in original.items():
                with self.subTest(code=values["code"]):
                    sequence = model.objects.get(pk=pk)
                    code = expected[sequence.code]
                    self.assertEqual(
                        sequence.document_type_id,
                        document_types[code].pk if code else None,
                    )
                    current = model.objects.values().get(pk=pk)
                    current.pop("document_type_id")
                    self.assertEqual(current, values)

            # A known code assigned to another type, and an unknown code with a
            # mapped type, must both survive the reverse data operation.
            other_branch = state.apps.get_model("core", "Branch").objects.create(
                company_id=company.pk, code="002", name="Sucursal",
            )
            reassigned = model.objects.create(
                company_id=company.pk, branch=other_branch, code="SAL", name="Reasignada",
                prefix="ALT-", document_type_id=document_types["PURCHASE_INVOICE"].pk,
            )
            custom = model.objects.create(
                company_id=company.pk, branch=other_branch, code="CUSTOM", name="Manual",
                prefix="ALT-", document_type_id=document_types["SALES_INVOICE"].pk,
            )
            migration = executor.loader.get_migration("core", "0005_sequence_document_type")
            with connection.schema_editor() as schema_editor:
                migration.operations[1].database_forwards("core", schema_editor, state, state)
                migration.operations[1].database_backwards("core", schema_editor, state, state)
            self.assertFalse(model.objects.filter(pk__in=original, document_type__isnull=False).exists())
            reassigned.refresh_from_db()
            custom.refresh_from_db()
            self.assertEqual(reassigned.document_type_id, document_types["PURCHASE_INVOICE"].pk)
            self.assertEqual(custom.document_type_id, document_types["SALES_INVOICE"].pk)

            executor = MigrationExecutor(connection)
            executor.migrate(before)
            model = executor.loader.project_state(before).apps.get_model("core", "Sequence")
            for pk, values in original.items():
                self.assertEqual(model.objects.values().get(pk=pk), values)
            # Remove the two post-migration examples before replaying the initial
            # mapping: their manually assigned types cannot survive column removal.
            model.objects.filter(pk__in=[reassigned.pk, custom.pk]).delete()
        finally:
            # Historical fixtures intentionally include unclassified sequences.
            # Remove test data before restoring the final NOT NULL schema.
            historical_sequence = executor.loader.project_state(before).apps.get_model("core", "Sequence")
            historical_sequence.objects.all().delete()
            MigrationExecutor(connection).migrate(latest)
