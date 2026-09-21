"""C-03: competencia real entre conexiones PostgreSQL, sin mocks ni skips."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.core.management import call_command
from django.db import connection, connections
from django.test import TransactionTestCase

from core.constants.document_status import DocumentStatus
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from purchases.models import Purchase
from purchases.tests.purchase_return_test_support import (
    REJECTIONS, PurchaseReturnFixture, movements, return_api, return_models,
)
from purchases.use_cases.cancel_purchase import CancelPurchase


class PurchaseReturnConcurrencyTests(PurchaseReturnFixture, TransactionTestCase):
    # Restaura los seeds reales de migraciones, nunca inventa PURCHASE_RETURN.
    serialized_rollback = True

    @classmethod
    def _fixture_setup(cls):
        # Otros TransactionTestCase regeneran ContentType durante su flush.
        # Vaciar exclusivamente la DB de tests antes de restaurar los seeds reales
        # evita colisiones de PK/natural key y dependencias del orden de la suite.
        for alias in cls._databases_names(include_mirrors=False):
            call_command("flush", database=alias, interactive=False, verbosity=0,
                         inhibit_post_migrate=True)
        super()._fixture_setup()

    def compete(self, left, right, *, require_purchase_locks=(True, True),
                synchronize_purchase_read=True):
        self.assertEqual(connection.vendor, "postgresql")
        before_purchase_read = Barrier(2)
        purchase_table = connection.ops.quote_name(Purchase._meta.db_table).upper()

        def run(operation):
            first_purchase_read = True
            purchase_locks = []

            def synchronize(execute, sql, params, many, context):
                nonlocal first_purchase_read
                statement = sql.lstrip().upper()
                if statement.startswith("SELECT") and f"FROM {purchase_table}" in statement:
                    if first_purchase_read:
                        first_purchase_read = False
                        if synchronize_purchase_read:
                            before_purchase_read.wait(timeout=10)
                    if "FOR UPDATE" in statement:
                        purchase_locks.append(statement)
                # SQL real; nunca espera después de adquirir el lock de Purchase.
                return execute(sql, params, many, context)

            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '20s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_pid = cursor.fetchone()[0]
                with connection.execute_wrapper(synchronize):
                    if not synchronize_purchase_read:
                        before_purchase_read.wait(timeout=10)
                    try:
                        operation()
                    except REJECTIONS as error:
                        outcome = ("rejected", type(error), str(error))
                    else:
                        outcome = ("success", None, "")
                return backend_pid, outcome, bool(purchase_locks)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, operation) for operation in (left, right)]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(len({pid for pid, _, _ in results}), 2)
        for (_, outcome, locked), required in zip(results, require_purchase_locks):
            if required:
                self.assertTrue(locked, "La operación debe serializar mediante lock de Purchase.")
            if outcome[0] == "rejected":
                self.assertTrue(issubclass(outcome[1], REJECTIONS))
                self.assertTrue(outcome[2], "El rechazo debe informar su causa de dominio.")
        return [outcome for _, outcome, _ in results]

    def test_return_vs_return_exactly_one_of_two_sevens_confirms(self):
        _, _, _, Confirm, _ = return_api()
        a = self.make_return("7")
        b = self.make_return("7")
        sequence = self.return_sequence()
        next_number = sequence.next_number
        outcomes = self.compete(
            lambda: Confirm.execute(purchase_return_id=a.pk, user=None),
            lambda: Confirm.execute(purchase_return_id=b.pk, user=None))
        self.assertCountEqual([outcome[0] for outcome in outcomes], ["success", "rejected"])
        rejection = next(outcome for outcome in outcomes if outcome[0] == "rejected")
        self.assertRegex(rejection[2].lower(), r"cantidad|quantity|devol|return|disponible|exced|saldo")
        Return, Detail = return_models()
        self.assertEqual(Return.objects.filter(purchase=self.purchase, status=DocumentStatus.CONFIRMED).count(), 1)
        quantities = Detail.objects.filter(purchase_detail=self.purchase.details.get(),
                                          purchase_return__status=DocumentStatus.CONFIRMED)
        quantity = sum(quantities.values_list("quantity", flat=True), Decimal("0"))
        self.assertEqual(quantity, Decimal("7"))
        self.assertLessEqual(quantity, self.purchase.details.get().quantity)
        self.assertEqual(self.stock().quantity, Decimal("3"))
        for document in (a, b):
            document.refresh_from_db()
            if document.status == DocumentStatus.CONFIRMED:
                movement = movements(document).get()
                self.assertEqual((movement.movement_type, movement.quantity, movement.reverses_id),
                                 (MovementType.RETURN_OUT, Decimal("7"), None))
                self.assertEqual(movement.document, document)
                self.assertTrue(document.number)
            else:
                self.assertEqual((document.status, document.number), (DocumentStatus.DRAFT, ""))
                self.assertFalse(movements(document).exists())
        sequence.refresh_from_db()
        self.assertEqual(sequence.next_number, next_number + 1)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_confirm_return_vs_cancel_purchase_has_only_two_consistent_outcomes(self):
        _, _, _, Confirm, _ = return_api()
        document = self.make_return("3")
        sequence = self.return_sequence()
        next_number = sequence.next_number
        original_purchase = movements(self.purchase, MovementType.PURCHASE).get()
        confirmed, cancelled = self.compete(
            lambda: Confirm.execute(purchase_return_id=document.pk, user=None),
            lambda: CancelPurchase.execute(purchase_id=self.purchase.pk, user=None))
        document.refresh_from_db()
        self.purchase.refresh_from_db()
        sequence.refresh_from_db()
        self.assertNotEqual((self.purchase.status, document.status),
                            (DocumentStatus.CANCELLED, DocumentStatus.CONFIRMED))
        self.assertCountEqual([confirmed[0], cancelled[0]], ["success", "rejected"])
        if confirmed[0] == "success":
            self.assertEqual((self.purchase.status, document.status),
                             (DocumentStatus.CONFIRMED, DocumentStatus.CONFIRMED))
            self.assertEqual(self.stock().quantity, Decimal("7"))
            outgoing = movements(document).get()
            self.assertEqual((outgoing.movement_type, outgoing.quantity, outgoing.reverses_id),
                             (MovementType.RETURN_OUT, Decimal("3"), None))
            self.assertEqual(outgoing.document, document)
            self.assertFalse(original_purchase.reversal_movements.exists())
            self.assertEqual(sequence.next_number, next_number + 1)
            self.assertTrue(document.number)
        else:
            self.assertEqual((self.purchase.status, document.status),
                             (DocumentStatus.CANCELLED, DocumentStatus.DRAFT))
            self.assertEqual(self.stock().quantity, Decimal("0"))
            self.assertFalse(movements(document).exists())
            self.assertEqual(document.number, "")
            self.assert_reversal(self.purchase, original_purchase, MovementType.RETURN_OUT)
            self.assertEqual(sequence.next_number, next_number)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_cancel_return_vs_cancel_purchase_never_double_compensates(self):
        _, _, _, _, Cancel = return_api()
        document = self.confirm_return(self.make_return("3"))
        original_return = movements(document, MovementType.RETURN_OUT).get()
        original_purchase = movements(self.purchase, MovementType.PURCHASE).get()
        sequence = self.return_sequence()
        next_number = sequence.next_number
        number = document.number
        cancelled_return, cancelled_purchase = self.compete(
            lambda: Cancel.execute(purchase_return_id=document.pk, user=None),
            lambda: CancelPurchase.execute(purchase_id=self.purchase.pk, user=None),
            # Aquí se evalúan invariantes; no se presupone la decisión de lock
            # adicional de CancelPurchaseReturn que este contrato busca evaluar.
            require_purchase_locks=(False, True), synchronize_purchase_read=False)
        self.assertEqual(cancelled_return[0], "success")
        self.assertIn(cancelled_purchase[0], ("success", "rejected"))
        document.refresh_from_db()
        self.purchase.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.CANCELLED)
        self.assertEqual(document.number, number)
        self.assert_reversal(document, original_return, MovementType.RETURN_IN)
        self.assertEqual(original_return.reversal_movements.count(), 1)
        if cancelled_purchase[0] == "success":
            self.assertEqual(self.purchase.status, DocumentStatus.CANCELLED)
            self.assertEqual(self.stock().quantity, Decimal("0"))
            self.assert_reversal(self.purchase, original_purchase, MovementType.RETURN_OUT)
            self.assertEqual(StockMovement.objects.count(), 4)
        else:
            self.assertEqual(self.purchase.status, DocumentStatus.CONFIRMED)
            self.assertEqual(self.stock().quantity, Decimal("10"))
            self.assertFalse(original_purchase.reversal_movements.exists())
            self.assertEqual(StockMovement.objects.count(), 3)
        sequence.refresh_from_db()
        self.assertEqual(sequence.next_number, next_number)

    def test_existing_purchase_cancellation_validates_real_two_connection_harness(self):
        original = movements(self.purchase, MovementType.PURCHASE).get()
        outcomes = self.compete(
            lambda: CancelPurchase.execute(purchase_id=self.purchase.pk, user=None),
            lambda: CancelPurchase.execute(purchase_id=self.purchase.pk, user=None))
        self.assertCountEqual(outcomes, [
            ("success", None, ""), ("rejected", ValueError, "El documento ya fue anulado.")])
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, DocumentStatus.CANCELLED)
        self.assertEqual(self.stock().quantity, Decimal("0"))
        self.assert_reversal(self.purchase, original, MovementType.RETURN_OUT)
        self.assertEqual(StockMovement.objects.count(), 2)
