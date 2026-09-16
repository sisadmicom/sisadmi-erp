"""Concurrencia real PostgreSQL; execute_wrapper sincroniza SQL, no lo simula."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import connection, connections
from django.test import TransactionTestCase

from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement
from inventory.services.stock import IncreaseStock
from inventory.tests.adjustment_test_support import (
    AdjustmentDataset, AdjustmentFixture, QUANTITY, REJECTIONS,
)


class PostgreSQLRace:
    def race(self, operations, model, *, synchronize_absent_read=False):
        self.assertEqual(connection.vendor, "postgresql")
        before_read = Barrier(2)
        after_read = Barrier(2)
        table = connection.ops.quote_name(model._meta.db_table).upper()

        def run(operation):
            first_read = True

            def synchronized_sql(execute, sql, params, many, context):
                nonlocal first_read
                statement = sql.lstrip().upper()
                if not (first_read and statement.startswith("SELECT") and f"FROM {table}" in statement):
                    return execute(sql, params, many, context)
                first_read = False
                before_read.wait(timeout=10)
                result = execute(sql, params, many, context)
                # Para Stock ausente ambas consultas reales deben observar ausencia
                # antes de insertar. Para cabecera, no esperar después de tomar lock.
                if synchronize_absent_read or "FOR UPDATE" not in statement:
                    after_read.wait(timeout=10)
                return result

            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '20s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pid = cursor.fetchone()[0]
                with connection.execute_wrapper(synchronized_sql):
                    try:
                        operation()
                    except REJECTIONS:
                        outcome = "rejected"
                    else:
                        outcome = "success"
                if first_read:
                    raise AssertionError("La operación no leyó la tabla esperada.")
                return pid, outcome
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(len({pid for pid, _ in results}), 2)
        return sorted(outcome for _, outcome in results)


class AdjustmentConcurrencyTests(AdjustmentFixture, PostgreSQLRace, TransactionTestCase):
    def test_two_confirmations_apply_one_effect_and_consume_one_number(self):
        stock = self.stock()
        adjustment = self.create()
        result = self.race([lambda: self.confirm(adjustment)] * 2, self.Adjustment)
        self.assertEqual(result, ["rejected", "success"])
        stock.refresh_from_db()
        adjustment.refresh_from_db()
        self.sequences["IN"].refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("10.004000"))
        self.assertEqual(adjustment.status, "CONFIRMED")
        self.assertTrue(adjustment.number)
        self.assertEqual(self.sequences["IN"].next_number, 2)
        movement = self.movements(adjustment).get()
        self.assertEqual(movement.quantity, QUANTITY)
        self.assertEqual(movement.movement_type, MovementType.ADJUSTMENT_IN)

    def test_two_cancellations_create_one_compensation_per_original(self):
        first_stock = self.stock()
        second_stock = self.stock(self.second_product)
        adjustment = self.create(details=[self.line(self.product), self.line(self.second_product)])
        self.confirm(adjustment)
        adjustment.refresh_from_db()
        number = adjustment.number
        originals = list(self.movements(adjustment))
        result = self.race([lambda: self.cancel(adjustment)] * 2, self.Adjustment)
        self.assertEqual(result, ["rejected", "success"])
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, "CANCELLED")
        self.assertEqual(adjustment.number, number)
        self.assertEqual(self.movements(adjustment).count(), 4)
        for stock in (first_stock, second_stock):
            stock.refresh_from_db()
            self.assertEqual(stock.quantity, Decimal("10"))
        for original in originals:
            reversal = original.reversal_movements.get()
            self.assertEqual(reversal.quantity, QUANTITY)
            self.assertEqual(reversal.movement_type, MovementType.RETURN_OUT)
        self.sequences["IN"].refresh_from_db()
        self.assertEqual(self.sequences["IN"].next_number, 2)

    def test_two_out_documents_cannot_overspend_same_stock(self):
        stock = self.stock(quantity="0.006000")
        first, second = self.create("OUT"), self.create("OUT")
        result = self.race([
            lambda: self.confirm(first), lambda: self.confirm(second),
        ], self.Adjustment)
        self.assertEqual(result, ["rejected", "success"])
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("0.002000"))
        self.assertEqual(self.Adjustment.objects.filter(status="CONFIRMED").count(), 1)
        draft = self.Adjustment.objects.get(status="DRAFT")
        self.assertEqual(draft.number, "")
        self.assertFalse(self.movements(draft).exists())
        movement = StockMovement.objects.get()
        self.assertEqual(movement.quantity, QUANTITY)
        self.assertEqual(movement.movement_type, MovementType.ADJUSTMENT_OUT)
        self.sequences["OUT"].refresh_from_db()
        self.assertEqual(self.sequences["OUT"].next_number, 2)


class InitialStockConcurrencyTests(AdjustmentDataset, PostgreSQLRace, TransactionTestCase):
    def test_concurrent_increase_creates_one_stock_and_preserves_both_effects(self):
        self.assertFalse(Stock.objects.exists())

        def increase():
            IncreaseStock().execute(
                company=self.company, branch=self.branch, warehouse=self.warehouse,
                product=self.product, quantity=QUANTITY,
                movement_type=MovementType.ADJUSTMENT_IN,
            )

        result = self.race([increase, increase], Stock, synchronize_absent_read=True)
        self.assertEqual(result, ["success", "success"])
        stock = Stock.objects.get()
        self.assertEqual(stock.quantity, Decimal("0.008000"))
        self.assertEqual(stock.reserved_quantity, Decimal("0"))
        self.assertEqual(list(StockMovement.objects.values_list("quantity", flat=True)), [QUANTITY, QUANTITY])
        self.assertEqual(set(StockMovement.objects.values_list("movement_type", flat=True)), {MovementType.ADJUSTMENT_IN})
