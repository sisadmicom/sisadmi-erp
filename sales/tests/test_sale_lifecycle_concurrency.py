from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.contrib.contenttypes.models import ContentType
from django.db import connection, connections
from django.test import TransactionTestCase

from core.constants.document_status import DocumentStatus
from core.exceptions.inventory import InventoryException
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement
from sales.models import Sale
from sales.tests.test_confirm_sale import SaleFixture
from sales.use_cases.cancel_sale import CancelSale
from sales.use_cases.confirm_sale import ConfirmSale


class SaleLifecycleConcurrencyTest(SaleFixture, TransactionTestCase):
    maxDiff = None

    def run_competing_operations(self, operation, sale_id):
        self.assertEqual(connection.vendor, "postgresql")
        before_read = Barrier(2)
        after_unlocked_read = Barrier(2)
        sale_table = connection.ops.quote_name(Sale._meta.db_table).upper()

        def run():
            first_sale_read = True

            def synchronize_read(execute, sql, params, many, context):
                nonlocal first_sale_read
                statement = sql.lstrip().upper()
                if not (
                    first_sale_read
                    and statement.startswith("SELECT")
                    and f"FROM {sale_table}" in statement
                ):
                    return execute(sql, params, many, context)

                first_sale_read = False
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
                        operation(sale_id=sale_id, user=None)
                    except (ValueError, InventoryException) as error:
                        outcome = (type(error).__name__, str(error))
                    else:
                        outcome = ("success", "")
                if first_sale_read:
                    raise AssertionError("La operación no consultó la cabecera Sale.")
                return backend_pid, outcome
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(len({pid for pid, _ in results}), 2)
        return sorted(outcome for _, outcome in results)

    def test_concurrent_confirmation_executes_sale_once(self):
        sale = self.create_sale("5")
        first_number = self.sequence.next_number
        expected_number = (
            f"{self.sequence.prefix}{self.sequence.series}-"
            f"{str(first_number).zfill(self.sequence.padding)}"
        )

        outcomes = self.run_competing_operations(ConfirmSale.execute, sale.pk)

        sale.refresh_from_db()
        self.sequence.refresh_from_db()
        stock = Stock.objects.get(warehouse=self.warehouse, product=self.product)
        movements = StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(Sale),
            object_id=sale.pk,
            movement_type=MovementType.SALE,
        )
        self.assertIsNotNone(sale.confirmed_at)
        self.assertEqual(
            {
                "outcomes": outcomes,
                "status": sale.status,
                "number": sale.number,
                "next_number": self.sequence.next_number,
                "stock": stock.quantity,
                "sale_quantities": list(movements.order_by("id").values_list("quantity", flat=True)),
                "movement_count": StockMovement.objects.count(),
            },
            {
                "outcomes": sorted([
                    ("success", ""),
                    ("ValueError", "Solo se pueden confirmar documentos en borrador."),
                ]),
                "status": DocumentStatus.CONFIRMED,
                "number": expected_number,
                "next_number": first_number + 1,
                "stock": Decimal("15"),
                "sale_quantities": [Decimal("5")],
                "movement_count": 1,
            },
        )

    def test_concurrent_cancellation_rejects_by_persisted_lifecycle(self):
        sale = self.create_sale("5")
        ConfirmSale.execute(sale_id=sale.pk, user=None)
        sale.refresh_from_db()
        self.sequence.refresh_from_db()
        confirmed_number = sale.number
        next_number = self.sequence.next_number
        originals = list(StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(Sale),
            object_id=sale.pk,
            movement_type=MovementType.SALE,
            reverses__isnull=True,
        ).order_by("id"))
        self.assertEqual(len(originals), 1)

        outcomes = self.run_competing_operations(CancelSale.execute, sale.pk)

        sale.refresh_from_db()
        self.sequence.refresh_from_db()
        stock = Stock.objects.get(warehouse=self.warehouse, product=self.product)
        for original in originals:
            self.assertEqual(original.reversal_movements.count(), 1)
            reversal = original.reversal_movements.get()
            self.assertEqual(reversal.movement_type, MovementType.RETURN_IN)
            self.assertEqual(reversal.quantity, original.quantity)
            self.assertEqual(reversal.warehouse_id, original.warehouse_id)
            self.assertEqual(reversal.product_id, original.product_id)
            self.assertEqual(reversal.content_type_id, original.content_type_id)
            self.assertEqual(reversal.object_id, original.object_id)
        self.assertIsNotNone(sale.cancelled_at)
        self.assertEqual(
            {
                "outcomes": outcomes,
                "status": sale.status,
                "number": sale.number,
                "next_number": self.sequence.next_number,
                "stock": stock.quantity,
                "original_count": StockMovement.objects.filter(
                    movement_type=MovementType.SALE, reverses__isnull=True,
                ).count(),
                "compensation_count": StockMovement.objects.filter(
                    movement_type=MovementType.RETURN_IN, reverses__isnull=False,
                ).count(),
                "movement_count": StockMovement.objects.count(),
            },
            {
                "outcomes": sorted([
                    ("success", ""),
                    ("ValueError", "El documento ya fue anulado."),
                ]),
                "status": DocumentStatus.CANCELLED,
                "number": confirmed_number,
                "next_number": next_number,
                "stock": Decimal("20"),
                "original_count": len(originals),
                "compensation_count": len(originals),
                "movement_count": 2 * len(originals),
            },
        )
