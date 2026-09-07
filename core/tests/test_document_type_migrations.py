from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class DocumentTypeMigrationTest(TransactionTestCase):
    def test_backfill_preserves_existing_documents_and_requires_type(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [
            ("sales", "0002_saledetailtax"),
            ("purchases", "0001_initial"),
            ("inventory", "0003_transfer_transferdetail"),
            ("core", "0004_seed_document_types"),
        ]
        try:
            executor.migrate(before)
            apps = executor.loader.project_state(before).apps
            person = apps.get_model("people", "Person").objects.create(
                identification="1790000001001", person_type="LEGAL", full_name="Empresa",
            )
            company = apps.get_model("core", "Company").objects.create(person=person)
            branch = apps.get_model("core", "Branch").objects.create(
                company=company, code="001", name="Matriz",
            )
            warehouse_model = apps.get_model("inventory", "Warehouse")
            source = warehouse_model.objects.create(
                company=company, branch=branch, code="SRC", name="Origen",
            )
            destination = warehouse_model.objects.create(
                company=company, branch=branch, code="DST", name="Destino",
            )
            customer = apps.get_model("people", "Customer").objects.create(person=person)
            supplier = apps.get_model("people", "Supplier").objects.create(person=person)
            cases = [
                ("sales", "Sale", "SALES_INVOICE", dict(customer=customer, warehouse=source)),
                ("purchases", "Purchase", "PURCHASE_INVOICE", dict(supplier=supplier)),
                ("inventory", "Transfer", "INVENTORY_TRANSFER", dict(
                    source_warehouse=source, destination_warehouse=destination,
                )),
            ]
            records = []
            for app, name, code, fields in cases:
                document = apps.get_model(app, name).objects.create(
                    company=company, branch=branch, number="LEGACY-001",
                    notes="Conservar", status="CONFIRMED", **fields,
                )
                records.append((app, name, code, document.pk))

            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            for app, name, code, pk in records:
                with self.subTest(model=name):
                    model = apps.get_model(app, name)
                    document = model.objects.get(pk=pk)
                    self.assertEqual(document.document_type.code, code)
                    self.assertEqual(document.number, "LEGACY-001")
                    self.assertEqual(document.notes, "Conservar")
                    self.assertEqual(document.status, "CONFIRMED")
                    self.assertEqual(document.company_id, company.pk)
                    self.assertEqual(document.branch_id, branch.pk)
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        model.objects.filter(pk=pk).update(document_type_id=None)
            migration_names = {
                "sales": "0003_sale_document_type",
                "purchases": "0002_purchase_document_type",
                "inventory": "0004_transfer_document_type",
            }
            for app, name, code, pk in records:
                with self.subTest(rollback=name):
                    migration = executor.loader.get_migration(app, migration_names[app])
                    nullable_state = executor.loader.project_state(before)
                    migration.operations[0].state_forwards(app, nullable_state)
                    required_state = nullable_state.clone()
                    migration.operations[2].state_forwards(app, required_state)
                    model = nullable_state.apps.get_model(app, name)
                    other_type = nullable_state.apps.get_model(
                        "core", "DocumentType",
                    ).objects.exclude(code=code).first()
                    other = model.objects.get(pk=pk)
                    other.pk = None
                    other.number = "OTHER-001"
                    other.document_type_id = other_type.pk
                    other.save()

                    with connection.schema_editor() as schema_editor:
                        migration.operations[2].database_backwards(
                            app, schema_editor, required_state, nullable_state,
                        )
                    untyped = model.objects.get(pk=pk)
                    untyped.pk = None
                    untyped.number = "NULL-001"
                    untyped.document_type_id = None
                    untyped.save()
                    try:
                        with connection.schema_editor() as schema_editor:
                            migration.operations[1].database_backwards(
                                app, schema_editor, nullable_state, nullable_state,
                            )
                        self.assertIsNone(model.objects.get(pk=pk).document_type_id)
                        other.refresh_from_db()
                        self.assertEqual(other.document_type_id, other_type.pk)
                        untyped.refresh_from_db()
                        self.assertIsNone(untyped.document_type_id)
                        self.assertEqual(model.objects.get(pk=pk).notes, "Conservar")
                    finally:
                        with connection.schema_editor() as schema_editor:
                            migration.operations[1].database_forwards(
                                app, schema_editor, nullable_state, nullable_state,
                            )
                            migration.operations[2].database_forwards(
                                app, schema_editor, nullable_state, required_state,
                            )

            executor = MigrationExecutor(connection)
            executor.migrate(before)
            apps = executor.loader.project_state(before).apps
            for app, name, code, pk in records:
                with self.subTest(full_rollback=name):
                    model = apps.get_model(app, name)
                    self.assertNotIn("document_type", {f.name for f in model._meta.fields})
                    document = model.objects.get(pk=pk)
                    self.assertEqual(document.number, "LEGACY-001")
                    self.assertEqual(document.notes, "Conservar")
                    self.assertEqual(document.status, "CONFIRMED")
                    self.assertEqual(document.company_id, company.pk)
                    self.assertEqual(document.branch_id, branch.pk)
        finally:
            MigrationExecutor(connection).migrate(latest)
