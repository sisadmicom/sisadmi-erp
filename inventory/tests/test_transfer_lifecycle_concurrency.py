from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.contrib.contenttypes.models import ContentType
from django.db import connection, connections
from django.test import TransactionTestCase

from core.constants.document_status import DocumentStatus
from core.exceptions.inventory import InventoryException
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Transfer
from inventory.tests.test_confirm_transfer import TransferFixture
from inventory.use_cases.cancel_transfer import CancelTransfer
from inventory.use_cases.confirm_transfer import ConfirmTransfer


class TransferLifecycleConcurrencyTest(TransferFixture, TransactionTestCase):
    maxDiff = None

    def run_competing_operations(self, operation, transfer_id):
        self.assertEqual(connection.vendor, "postgresql")
        before_read = Barrier(2)
        after_unlocked_read = Barrier(2)
        transfer_table = connection.ops.quote_name(Transfer._meta.db_table).upper()

        def run():
            first_transfer_read = True

            def synchronize_read(execute, sql, params, many, context):
                nonlocal first_transfer_read
                statement = sql.lstrip().upper()
                if not (
                    first_transfer_read
                    and statement.startswith("SELECT")
                    and f"FROM {transfer_table}" in statement
                ):
                    return execute(sql, params, many, context)

                first_transfer_read = False
                before_read.wait(timeout=10)
                result = execute(sql, params, many, context)
                # Ejecutamos SQL real. Con la lectura actual sin lock, ambas
                # consultas deben terminar antes de que cualquiera continúe.
                # Una futura lectura FOR UPDATE se serializa en PostgreSQL:
                # no esperar al segundo thread DESPUÉS de adquirir ese lock.
                if "FOR UPDATE" not in statement:
                    after_unlocked_read.wait(timeout=10)
                return result

            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '20s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_pid = cursor.fetchone()[0]
                with connection.execute_wrapper(synchronize_read):
                    try:
                        operation(transfer_id=transfer_id, user=None)
                    except (ValueError, InventoryException) as error:
                        outcome = (type(error).__name__, str(error))
                    else:
                        outcome = ("success", "")
                if first_transfer_read:
                    raise AssertionError("La operación no consultó la cabecera Transfer.")
                return backend_pid, outcome
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(len({pid for pid, _ in results}), 2)
        return sorted(outcome for _, outcome in results)

    def document_movements(self, transfer):
        return StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(Transfer),
            object_id=transfer.pk,
        ).order_by("id")

    def warehouse_quantities(self):
        return {
            warehouse.pk: Stock.objects.get(
                warehouse=warehouse, product=self.product,
            ).quantity
            for warehouse in (self.source_warehouse, self.destination_warehouse)
        }

    def test_concurrent_confirmation_executes_transfer_once(self):
        # Esta fixture tiene una línea: exactamente un OUT y un IN.
        transfer = self.create_transfer("5")
        first_number = self.sequence.next_number
        expected_number = (
            f"{self.sequence.prefix}{self.sequence.series}-"
            f"{str(first_number).zfill(self.sequence.padding)}"
        )
        outcomes = self.run_competing_operations(ConfirmTransfer.execute, transfer.pk)
        transfer.refresh_from_db()
        self.sequence.refresh_from_db()
        self.assertIsNotNone(transfer.confirmed_at)
        self.assertEqual(
            {
                "outcomes": outcomes,
                "status": transfer.status,
                "number": transfer.number,
                "next_number": self.sequence.next_number,
                "stocks": self.warehouse_quantities(),
                "movements": list(self.document_movements(transfer).values_list(
                    "movement_type", "product_id", "warehouse_id", "quantity", "reverses_id",
                )),
            },
            {
                "outcomes": sorted([
                    ("success", ""),
                    ("ValueError", "Solo se pueden confirmar documentos en borrador."),
                ]),
                "status": DocumentStatus.CONFIRMED,
                "number": expected_number,
                "next_number": first_number + 1,
                "stocks": {self.source_warehouse.pk: Decimal("15"), self.destination_warehouse.pk: Decimal("10")},
                "movements": [
                    (MovementType.TRANSFER_OUT, self.product.pk, self.source_warehouse.pk, Decimal("5"), None),
                    (MovementType.TRANSFER_IN, self.product.pk, self.destination_warehouse.pk, Decimal("5"), None),
                ],
            },
        )

    def test_concurrent_cancellation_rejects_by_persisted_lifecycle(self):
        transfer = self.create_transfer("5")
        ConfirmTransfer.execute(transfer_id=transfer.pk, user=None)
        transfer.refresh_from_db()
        self.sequence.refresh_from_db()
        number, next_number = transfer.number, self.sequence.next_number
        confirmed_at, confirmed_by = transfer.confirmed_at, transfer.confirmed_by_id
        originals = list(self.document_movements(transfer))
        self.assertCountEqual(
            [original.movement_type for original in originals],
            [MovementType.TRANSFER_OUT, MovementType.TRANSFER_IN],
        )
        outcomes = self.run_competing_operations(CancelTransfer.execute, transfer.pk)
        transfer.refresh_from_db()
        self.sequence.refresh_from_db()
        self.assertIsNotNone(transfer.cancelled_at)
        expected_types = {
            MovementType.TRANSFER_IN: MovementType.RETURN_OUT,
            MovementType.TRANSFER_OUT: MovementType.RETURN_IN,
        }
        for original in originals:
            self.assertEqual(original.reversal_movements.count(), 1)
            reversal = original.reversal_movements.get()
            self.assertEqual(reversal.movement_type, expected_types[original.movement_type])
            for field in (
                "quantity", "unit_cost", "company_id", "branch_id",
                "warehouse_id", "product_id", "content_type_id", "object_id",
            ):
                self.assertEqual(getattr(reversal, field), getattr(original, field), field)
        # El orden global histórico debe ser IN->RETURN_OUT, luego OUT->RETURN_IN.
        self.assertEqual(
            list(self.document_movements(transfer).filter(reverses__isnull=False).values_list("movement_type", flat=True)),
            [MovementType.RETURN_OUT, MovementType.RETURN_IN],
        )
        self.assertEqual(
            {
                "outcomes": outcomes,
                "status": transfer.status,
                "number": transfer.number,
                "next_number": self.sequence.next_number,
                "confirmed_at": transfer.confirmed_at,
                "confirmed_by": transfer.confirmed_by_id,
                "stocks": self.warehouse_quantities(),
                "movement_count": self.document_movements(transfer).count(),
            },
            {
                "outcomes": sorted([
                    ("success", ""),
                    ("ValueError", "El documento ya fue anulado."),
                ]),
                "status": DocumentStatus.CANCELLED,
                "number": number,
                "next_number": next_number,
                "confirmed_at": confirmed_at,
                "confirmed_by": confirmed_by,
                "stocks": {self.source_warehouse.pk: Decimal("20"), self.destination_warehouse.pk: Decimal("5")},
                "movement_count": 2 * len(originals),
            },
        )
