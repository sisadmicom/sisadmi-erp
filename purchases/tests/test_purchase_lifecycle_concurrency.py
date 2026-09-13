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
from purchases.models import Purchase
from purchases.services.purchase_confirmation_service import PurchaseConfirmationService
from purchases.services.purchase_cancellation_service import PurchaseCancellationService
from purchases.tests.test_confirm_purchase import PurchaseFixture
from purchases.use_cases.confirm_purchase import ConfirmPurchase
from purchases.use_cases.cancel_purchase import CancelPurchase


def confirm_direct(*, purchase_id, user=None):
    return PurchaseConfirmationService.confirm(purchase_id=purchase_id, user=user)


def cancel_direct(*, purchase_id, user=None):
    return PurchaseCancellationService.cancel(purchase_id=purchase_id, user=user)


class PurchaseLifecycleConcurrencyTest(PurchaseFixture, TransactionTestCase):
    maxDiff = None

    def run_competing_operations(self, operation):
        self.assertEqual(connection.vendor, "postgresql")
        before_read = Barrier(2)
        after_unlocked_read = Barrier(2)
        purchase_table = connection.ops.quote_name(Purchase._meta.db_table).upper()
        purchase_id = self.purchase.pk

        def run():
            first_purchase_read = True

            def synchronize_read(execute, sql, params, many, context):
                nonlocal first_purchase_read
                statement = sql.lstrip().upper()
                if not (
                    first_purchase_read
                    and statement.startswith("SELECT")
                    and f"FROM {purchase_table}" in statement
                ):
                    return execute(sql, params, many, context)
                first_purchase_read = False
                before_read.wait(timeout=10)
                result = execute(sql, params, many, context)
                # Patrón de Sales: completar ambas lecturas ordinarias antes de
                # continuar. FOR UPDATE debe serializar en PostgreSQL; nunca
                # esperar a otro thread después de adquirir ese lock.
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
                        operation(purchase_id=purchase_id, user=None)
                    except (ValueError, InventoryException) as error:
                        outcome = (type(error).__name__, str(error))
                    else:
                        outcome = ("success", "")
                if first_purchase_read:
                    raise AssertionError("La operación no consultó la cabecera Purchase.")
                return backend_pid, outcome
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(len({pid for pid, _ in results}), 2)
        return sorted(outcome for _, outcome in results)

    def assert_single_confirmation(self, operation):
        first_number = self.sequence.next_number
        expected_number = (
            f"{self.sequence.prefix}{self.sequence.series}-"
            f"{str(first_number).zfill(self.sequence.padding)}"
        )
        outcomes = self.run_competing_operations(operation)
        self.purchase.refresh_from_db()
        self.sequence.refresh_from_db()
        movements = StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(Purchase),
            object_id=self.purchase.pk,
        ).order_by("pk")
        self.assertIsNotNone(self.purchase.confirmed_at)
        self.assertEqual(
            {
                "outcomes": outcomes,
                "status": self.purchase.status,
                "number": self.purchase.number,
                "next_number": self.sequence.next_number,
                "stocks": list(Stock.objects.filter(
                    product=self.product, warehouse=self.warehouse,
                ).values_list("quantity", flat=True)),
                "movements": list(movements.values_list("movement_type", "quantity", "reverses_id")),
            },
            {
                "outcomes": sorted([
                    ("success", ""),
                    ("ValueError", "Solo se pueden confirmar documentos en borrador."),
                ]),
                "status": DocumentStatus.CONFIRMED,
                "number": expected_number,
                "next_number": first_number + 1,
                "stocks": [Decimal("5")],
                "movements": [(MovementType.PURCHASE, Decimal("5"), None)],
            },
        )

    def assert_single_cancellation(self, operation):
        ConfirmPurchase.execute(purchase_id=self.purchase.pk, user=None)
        self.purchase.refresh_from_db()
        self.sequence.refresh_from_db()
        number = self.purchase.number
        next_number = self.sequence.next_number
        originals = list(StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(Purchase),
            object_id=self.purchase.pk,
            movement_type=MovementType.PURCHASE, reverses__isnull=True,
        ))
        self.assertEqual(len(originals), 1)
        outcomes = self.run_competing_operations(operation)

        self.purchase.refresh_from_db()
        self.sequence.refresh_from_db()
        for original in originals:
            self.assertEqual(original.reversal_movements.count(), 1)
            reversal = original.reversal_movements.get()
            self.assertEqual(reversal.movement_type, MovementType.RETURN_OUT)
            for field in (
                "quantity", "unit_cost", "company_id", "branch_id",
                "warehouse_id", "product_id", "content_type_id", "object_id",
            ):
                self.assertEqual(getattr(reversal, field), getattr(original, field), field)
        self.assertIsNotNone(self.purchase.cancelled_at)
        self.assertEqual(
            {
                "outcomes": outcomes,
                "status": self.purchase.status,
                "number": self.purchase.number,
                "next_number": self.sequence.next_number,
                "stock": Stock.objects.get(product=self.product, warehouse=self.warehouse).quantity,
                "movement_count": StockMovement.objects.count(),
            },
            {
                "outcomes": sorted([
                    ("success", ""),
                    ("ValueError", "El documento ya fue anulado."),
                ]),
                "status": DocumentStatus.CANCELLED,
                "number": number,
                "next_number": next_number,
                "stock": Decimal("0"),
                "movement_count": 2 * len(originals),
            },
        )

    def test_direct_confirmation_executes_purchase_once(self):
        self.assert_single_confirmation(confirm_direct)

    def test_direct_cancellation_rejects_by_persisted_lifecycle(self):
        self.assert_single_cancellation(cancel_direct)

    def test_confirm_use_case_already_serializes_purchase(self):
        self.assert_single_confirmation(ConfirmPurchase.execute)

    def test_cancel_use_case_already_serializes_purchase(self):
        self.assert_single_cancellation(CancelPurchase.execute)
