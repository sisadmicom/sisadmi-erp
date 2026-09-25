"""C-08: reuse the adjustment dataset; never synthesize a manifest model."""
from decimal import Decimal
from unittest.mock import patch

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from inventory.services.stock import IncreaseStock
from inventory.tests.adjustment_test_support import AdjustmentFixture, REJECTIONS


class AdjustmentManifestFixture(AdjustmentFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.stock(self.product, quantity="100")
        self.stock(self.second_product, quantity="100")

    def manifest_model(self):
        try:
            return apps.get_model("inventory", "InventoryAdjustmentMovement")
        except LookupError:
            return None

    def require_manifest_model(self):
        model = self.manifest_model()
        self.assertIsNotNone(model, "C-08 missing model: InventoryAdjustmentMovement")
        return model

    def make_adjustment(self, direction="IN", *, two=False, confirmed=True):
        details = [self.line(self.product, Decimal("3"))]
        if two:
            details.append(self.line(self.second_product, Decimal("2")))
        adjustment = self.create(direction, details=details)
        if confirmed:
            self.confirm(adjustment)
            adjustment.refresh_from_db()
            if self.manifest_model() is not None:
                # When implemented, every corruption starts from a complete real manifest.
                # No missing-capture defect may make a semantic rejection test pass early.
                self.assertEqual(self.manifest_ids(adjustment),
                                 set(self.originals(adjustment).values_list("pk", flat=True)))
        return adjustment

    def originals(self, adjustment):
        return StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(self.Adjustment),
            object_id=adjustment.pk,
            movement_type__in=[MovementType.ADJUSTMENT_IN, MovementType.ADJUSTMENT_OUT],
            reverses__isnull=True,
        ).order_by("pk")

    def manifest_ids(self, adjustment):
        model = self.require_manifest_model()
        return set(model.objects.filter(inventory_adjustment=adjustment).values_list(
            "stock_movement_id", flat=True))

    def state(self, adjustment):
        state = self.snapshot(adjustment)
        model = self.manifest_model()
        # Absence is observed, not replaced by a test implementation.
        state["manifest"] = None if model is None else list(model.objects.order_by("pk").values())
        return state

    def assert_cancel_rejected(self, adjustment, *, before_any_reverse=False):
        before = self.state(adjustment)
        with patch.object(StockMovementReversalService, "reverse",
                          wraps=StockMovementReversalService.reverse) as reverse:
            with self.assertRaises(REJECTIONS):
                self.cancel(adjustment)
        self.assertEqual(self.state(adjustment), before)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, "CONFIRMED")
        if before_any_reverse:
            reverse.assert_not_called()

    def add_extra_original(self, adjustment):
        return IncreaseStock().execute(
            company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=self.product, quantity=Decimal("1"),
            movement_type=MovementType.ADJUSTMENT_IN, document=adjustment,
            return_movement=True,
        )

    def assert_historical_reversal(self, original):
        original.refresh_from_db()
        self.assertIsNone(original.reverses_id)
        reversal = StockMovement.objects.get(reverses=original)
        self.assertEqual(reversal.reverses_id, original.pk)
        expected_type = (MovementType.RETURN_OUT if original.movement_type == MovementType.ADJUSTMENT_IN
                         else MovementType.RETURN_IN)
        self.assertEqual(reversal.movement_type, expected_type)
        for field in ("company_id", "branch_id", "product_id", "warehouse_id", "quantity",
                      "unit_cost", "content_type_id", "object_id"):
            self.assertEqual(getattr(reversal, field), getattr(original, field), field)
        return reversal
