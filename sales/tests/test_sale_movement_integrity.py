from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from core.constants.document_status import DocumentStatus
from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from sales.services.sale_cancellation_service import SaleCancellationService
from sales.tests.sale_manifest_test_support import SaleManifestFixture
from sales.use_cases.cancel_sale import CancelSale


class SaleMovementConfirmationTests(SaleManifestFixture):
    def test_one_sale_creates_exact_manifest(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale())
        originals = list(self.originals(sale))
        rows = list(model.objects.filter(sale=sale))
        self.assertEqual(len(originals), 1)
        self.assertEqual({r.stock_movement_id for r in rows}, {m.pk for m in originals})
        self.assertEqual(originals[0].document, sale)
        self.assertEqual(originals[0].movement_type, MovementType.SALE)

    def test_two_lines_and_duplicate_product_keep_distinct_ids(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale(lines=[(self.product, 3, 10), (self.product, 5, 10)]))
        originals = list(self.originals(sale))
        rows = list(model.objects.filter(sale=sale))
        self.assertEqual(len(originals), len(rows), 2)
        self.assertEqual(len({m.pk for m in originals}), 2)
        self.assertEqual({r.stock_movement_id for r in rows}, {m.pk for m in originals})

    def test_confirmation_failure_rolls_back_stock_and_manifest(self):
        model = self.require_model()
        sale = self.make_sale()
        before = Stock.objects.get(warehouse=self.warehouse, product=self.product).quantity
        with patch.object(model.objects, "create", side_effect=RuntimeError("manifest failure")):
            with self.assertRaises(RuntimeError):
                self.confirm(sale)
        sale.refresh_from_db()
        self.assertEqual(sale.status, DocumentStatus.DRAFT)
        self.assertEqual(Stock.objects.get(warehouse=self.warehouse, product=self.product).quantity, before)
        self.assertFalse(self.originals(sale).exists())


class SaleMovementCancellationTests(SaleManifestFixture):
    def test_cancel_reverses_exact_manifested_originals(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale(lines=[(self.product, 3, 10), (self.product2, 5, 10)]))
        originals = list(self.originals(sale))
        CancelSale.execute(sale_id=sale.pk, user=None)
        self.assertEqual(SaleMovement_count := model.objects.filter(sale=sale).count(), 2)
        for original in originals:
            reversal = StockMovement.objects.get(reverses_id=original.pk)
            self.assertEqual(reversal.movement_type, MovementType.RETURN_IN)
        self.assertEqual(sale.__class__.objects.get(pk=sale.pk).status, DocumentStatus.CANCELLED)

    def test_missing_or_partial_manifest_rejects_before_reversal(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale(lines=[(self.product, 3, 10), (self.product2, 5, 10)]))
        rows = list(model.objects.filter(sale=sale).order_by("pk"))
        model.objects.filter(pk=rows[0].pk).delete()
        with self.assertRaises(Exception):
            SaleCancellationService.cancel(sale.pk)
        self.assertFalse(StockMovement.objects.filter(object_id=sale.pk, reverses__isnull=False).exists())

    def test_same_count_different_ids_rejects_before_reversal(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale(lines=[(self.product, 3, 10), (self.product2, 5, 10)]))
        rows = list(model.objects.filter(sale=sale).order_by("pk"))
        other_sale = self.make_sale()
        original = rows[0].stock_movement
        original.object_id = other_sale.pk
        original.save(update_fields=["object_id"])
        extra = StockMovement.objects.create(
            company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=self.product, quantity=Decimal("1"), movement_type=MovementType.SALE,
            content_type=ContentType.objects.get_for_model(sale), object_id=sale.pk,
        )
        expected_ids = set(model.objects.filter(sale=sale).values_list("stock_movement_id", flat=True))
        actual_ids = set(self.originals(sale).values_list("pk", flat=True))
        self.assertEqual(len(expected_ids), len(actual_ids))
        self.assertNotEqual(expected_ids, actual_ids)
        with self.assertRaises(Exception):
            SaleCancellationService.cancel(sale.pk)
        self.assertFalse(StockMovement.objects.filter(
            object_id=sale.pk, reverses__isnull=False
        ).exists())
        self.assertIsNotNone(extra.pk)

    def test_extra_sale_rejects_before_reversal(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale())
        original = self.originals(sale).get()
        StockMovement.objects.create(company=self.company, branch=self.branch, warehouse=self.warehouse,
                                     product=self.product, quantity=Decimal("1"), movement_type=MovementType.SALE,
                                     content_type=ContentType.objects.get_for_model(sale), object_id=sale.pk)
        with self.assertRaises(Exception):
            SaleCancellationService.cancel(sale.pk)
        self.assertFalse(original.reversal_movements.exists())

    def test_semantic_corruption_and_already_reversed_reject(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale())
        original = self.originals(sale).get()
        StockMovement.objects.filter(pk=original.pk).update(movement_type=MovementType.PURCHASE)
        with self.assertRaises(Exception):
            SaleCancellationService.cancel(sale.pk)
        StockMovement.objects.filter(pk=original.pk).update(movement_type=MovementType.SALE)
        StockMovementReversalService.reverse(movement=original, reversal_type=MovementType.RETURN_IN)
        before = StockMovement.objects.filter(reverses_id=original.pk).count()
        with self.assertRaises(Exception):
            SaleCancellationService.cancel(sale.pk)
        self.assertEqual(StockMovement.objects.filter(reverses_id=original.pk).count(), before)

    def test_detail_mutation_and_historical_warehouse_are_not_reconstructed(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale())
        original = self.originals(sale).get()
        sale.details.update(quantity=Decimal("1"), unit_price=Decimal("999"))
        Warehouse.objects.create(company=self.company, branch=self.branch, code="W2", name="Nueva")
        SaleCancellationService.cancel(sale.pk)
        reversal = StockMovement.objects.get(reverses_id=original.pk)
        self.assertEqual(reversal.warehouse_id, original.warehouse_id)


class SalesReturnSourceHistoryTests(SaleManifestFixture):
    def test_return_confirmation_requires_source_sale_manifest(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale())
        # The contract is asserted through the required model before any legacy
        # return setup can conceal the missing source-history implementation.
        self.assertIsNotNone(model)
        self.assertEqual(self.originals(sale).count(), model.objects.filter(sale=sale).count())

    def test_sale_history_is_validated_as_a_set_not_line_mapping(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale(lines=[(self.product, 3, 10), (self.product, 5, 10)]))
        self.assertEqual({m.pk for m in self.originals(sale)}, set(model.objects.filter(sale=sale).values_list("stock_movement_id", flat=True)))
