from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connections
from django.test import TestCase, TransactionTestCase

from catalog.models import Product
from core.exceptions.inventory import InventoryException
from core.models import Branch, Company
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.movement.create_stock_movement import CreateStockMovement
from inventory.services.movement.stock_movement_reversal_service import (
    StockMovementReversalService,
)
from people.models import Person


class ReversalFixture:
    def setUp(self):
        super().setUp()
        person = Person.objects.create(
            identification="1790000001001",
            person_type="LEGAL",
            full_name="Empresa Test",
        )
        self.company = Company.objects.create(person=person, commercial_name="Test")
        self.branch = Branch.objects.create(
            company=self.company, code="001", name="Matriz",
        )
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, code="B001", name="Principal",
        )
        self.product = Product.objects.create(
            company=self.company, code="P001", name="Producto",
        )
        self.stock = Stock.objects.create(
            company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=self.product, quantity=Decimal("20"),
        )

    def create_original(self, movement_type=MovementType.SALE, **kwargs):
        return CreateStockMovement().execute(
            company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=self.product, quantity=Decimal("10"),
            unit_cost=Decimal("5.123456"), movement_type=movement_type, **kwargs,
        )

    def assert_stock(self, quantity):
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, Decimal(quantity))


class StockMovementReversalServiceTest(ReversalFixture, TestCase):
    def assert_compensation(self, original, reversal, reversal_type):
        self.assertIsInstance(reversal, StockMovement)
        reversal.refresh_from_db()
        self.assertEqual(reversal.reverses, original)
        for field in (
            "company_id", "branch_id", "warehouse_id", "product_id",
            "quantity", "unit_cost", "content_type_id", "object_id", "document",
        ):
            self.assertEqual(getattr(reversal, field), getattr(original, field), field)
        self.assertEqual(reversal.movement_type, reversal_type)
        self.assertEqual(original.reversal_movements.count(), 1)

    def test_output_to_input_preserves_history_and_user(self):
        # A generic reference exercises document preservation without commercial models.
        original = self.create_original(document=self.warehouse)
        user = get_user_model().objects.create_user(username="reversal-auditor")
        reversal = StockMovementReversalService.reverse(
            movement=original, reversal_type=MovementType.RETURN_IN, user=user,
        )
        self.assert_stock("30")
        self.assert_compensation(original, reversal, MovementType.RETURN_IN)
        self.assertEqual(reversal.created_by, user)

    def test_input_to_output_preserves_history(self):
        original = self.create_original(MovementType.PURCHASE)
        reversal = StockMovementReversalService.reverse(
            movement=original, reversal_type=MovementType.RETURN_OUT,
        )
        self.assert_stock("10")
        self.assert_compensation(original, reversal, MovementType.RETURN_OUT)

    def test_same_direction_is_rejected_without_effects(self):
        for original_type, reversal_type in (
            (MovementType.SALE, MovementType.ADJUSTMENT_OUT),
            (MovementType.PURCHASE, MovementType.ADJUSTMENT_IN),
        ):
            with self.subTest(original_type=original_type):
                original = self.create_original(original_type)
                count = StockMovement.objects.count()
                with self.assertRaises(InventoryException):
                    StockMovementReversalService.reverse(
                        movement=original, reversal_type=reversal_type,
                    )
                self.assert_stock("20")
                self.assertEqual(StockMovement.objects.count(), count)
                self.assertFalse(original.reversal_movements.exists())

    def test_unclassified_types_are_rejected_without_effects(self):
        for original_type, reversal_type in (
            ("UNKNOWN", MovementType.RETURN_IN),
            (MovementType.SALE, "UNKNOWN"),
        ):
            with self.subTest(original_type=original_type, reversal_type=reversal_type):
                original = self.create_original(original_type)
                count = StockMovement.objects.count()
                with self.assertRaises(InventoryException):
                    StockMovementReversalService.reverse(
                        movement=original, reversal_type=reversal_type,
                    )
                self.assert_stock("20")
                self.assertEqual(StockMovement.objects.count(), count)

    def test_double_reversal_is_rejected_even_with_prefetched_empty_relation(self):
        original = self.create_original()
        stale = StockMovement.objects.prefetch_related("reversal_movements").get(
            pk=original.pk,
        )
        StockMovementReversalService.reverse(
            movement=original, reversal_type=MovementType.RETURN_IN,
        )
        with self.assertRaises(InventoryException):
            StockMovementReversalService.reverse(
                movement=stale, reversal_type=MovementType.RETURN_IN,
            )
        self.assert_stock("30")
        self.assertEqual(original.reversal_movements.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_reversal_cannot_be_reversed_even_if_in_memory_link_is_removed(self):
        original = self.create_original()
        reversal = StockMovementReversalService.reverse(
            movement=original, reversal_type=MovementType.RETURN_IN,
        )
        reversal.reverses = None
        with self.assertRaises(InventoryException):
            StockMovementReversalService.reverse(
                movement=reversal, reversal_type=MovementType.RETURN_OUT,
            )
        self.assert_stock("30")
        self.assertEqual(StockMovement.objects.count(), 2)
        self.assertFalse(reversal.reversal_movements.exists())

    def test_insufficient_stock_has_no_effects(self):
        original = self.create_original(MovementType.PURCHASE)
        self.stock.quantity = Decimal("5")
        self.stock.save(update_fields=["quantity"])
        with self.assertRaisesMessage(ValidationError, "No existe stock suficiente."):
            StockMovementReversalService.reverse(
                movement=original, reversal_type=MovementType.RETURN_OUT,
            )
        self.assert_stock("5")
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertFalse(original.reversal_movements.exists())

    def test_uses_persisted_history_instead_of_mutated_instance(self):
        original = self.create_original(document=self.warehouse)
        persisted = StockMovement.objects.get(pk=original.pk)
        original.company = None
        original.branch = None
        original.warehouse = None
        original.product = None
        original.quantity = Decimal("999")
        original.unit_cost = Decimal("999")
        original.document = None
        original.movement_type = MovementType.PURCHASE
        reversal = StockMovementReversalService.reverse(
            movement=original, reversal_type=MovementType.ADJUSTMENT_IN,
        )
        self.assert_stock("30")
        self.assert_compensation(persisted, reversal, MovementType.ADJUSTMENT_IN)

    def test_failure_after_movement_creation_rolls_back_stock_and_compensation(self):
        original = self.create_original()
        create = CreateStockMovement.execute

        def create_then_fail(service, **kwargs):
            create(service, **kwargs)
            raise RuntimeError("Fallo de registro")

        with patch.object(CreateStockMovement, "execute", new=create_then_fail):
            with self.assertRaisesMessage(RuntimeError, "Fallo de registro"):
                StockMovementReversalService.reverse(
                    movement=original, reversal_type=MovementType.RETURN_IN,
                )
        self.assert_stock("20")
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertFalse(original.reversal_movements.exists())


class StockMovementReversalConcurrencyTest(ReversalFixture, TransactionTestCase):
    def test_concurrent_reversals_create_only_one_compensation(self):
        original = self.create_original()
        barrier = Barrier(2)

        def reverse():
            try:
                movement = StockMovement.objects.get(pk=original.pk)
                barrier.wait(timeout=10)
                try:
                    StockMovementReversalService.reverse(
                        movement=movement, reversal_type=MovementType.RETURN_IN,
                    )
                except InventoryException:
                    return "rejected"
                return "reversed"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(reverse) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertCountEqual(results, ["reversed", "rejected"])
        self.assert_stock("30")
        self.assertEqual(original.reversal_movements.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 2)
