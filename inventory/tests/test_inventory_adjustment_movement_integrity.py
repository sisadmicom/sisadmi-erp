"""C-08 membership validation and historical authority, using only legal ORM writes."""
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

from catalog.models import Product
from core.models import Branch, DocumentType
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from inventory.tests.adjustment_manifest_test_support import AdjustmentManifestFixture


class AdjustmentMovementIntegrityTests(AdjustmentManifestFixture):
    def test_missing_manifest_rejects_existing_operational_history(self):
        adjustment = self.make_adjustment()
        model = self.manifest_model()
        # Today there is no manifest at all; later remove the real persisted rows.
        # This neither creates a substitute model nor skips the rejection contract.
        if model is not None:
            model.objects.filter(inventory_adjustment=adjustment).delete()
        self.assertEqual(self.originals(adjustment).count(), 1)
        self.assert_cancel_rejected(adjustment, before_any_reverse=True)

    def test_partial_manifest_rejects_two_originals(self):
        model = self.require_manifest_model()
        adjustment = self.make_adjustment(two=True)
        self.assertEqual(self.manifest_ids(adjustment), set(self.originals(adjustment).values_list("pk", flat=True)))
        rows = model.objects.filter(inventory_adjustment=adjustment)
        rows.order_by("pk").last().delete()
        self.assertEqual(rows.count(), 1)
        self.assertEqual(self.originals(adjustment).count(), 2)
        self.assert_cancel_rejected(adjustment, before_any_reverse=True)

    def test_extra_original_same_product_is_not_membership(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        extra = self.add_extra_original(adjustment)
        self.assertEqual(extra.product_id, original.product_id)
        self.assertNotEqual(extra.pk, original.pk)
        self.assertEqual(adjustment.details.count(), 1)
        self.assertEqual(self.originals(adjustment).count(), 2)
        # Duplicate details are not needed: a separate legal stock effect has a distinct ID.
        self.assert_cancel_rejected(adjustment, before_any_reverse=True)

    def test_same_count_different_ids_rejects_despite_same_operational_values(self):
        model = self.require_manifest_model()
        adjustment = self.make_adjustment(two=True)
        expected = self.manifest_ids(adjustment)
        original = self.originals(adjustment).last()
        other = self.make_adjustment(confirmed=False)
        StockMovement.objects.filter(pk=original.pk).update(object_id=other.pk)
        values = {field: getattr(original, field) for field in (
            "company_id", "branch_id", "warehouse_id", "product_id", "movement_type",
            "quantity", "unit_cost", "content_type_id", "object_id")}
        replacement = StockMovement.objects.create(**values)
        self.assertNotEqual(replacement.pk, original.pk)
        actual = set(self.originals(adjustment).values_list("pk", flat=True))
        self.assertEqual(len(expected), len(actual))
        self.assertNotEqual(expected, actual)
        self.assertEqual(set(model.objects.filter(inventory_adjustment=adjustment).values_list(
            "stock_movement_id", flat=True)), expected)
        self.assert_cancel_rejected(adjustment, before_any_reverse=True)

    def test_manifest_cannot_borrow_another_adjustments_original(self):
        model = self.require_manifest_model()
        adjustment = self.make_adjustment()
        other = self.make_adjustment()
        foreign = self.originals(other).get()
        model.objects.filter(inventory_adjustment=other).delete()
        model.objects.filter(inventory_adjustment=adjustment).update(stock_movement=foreign)
        self.assertEqual(self.manifest_ids(adjustment), {foreign.pk})
        self.assertNotEqual(foreign.object_id, adjustment.pk)
        self.assert_cancel_rejected(adjustment, before_any_reverse=True)

    def test_wrong_movement_type_cannot_disappear_from_actual_set(self):
        adjustment = self.make_adjustment(two=True)
        invalid = self.originals(adjustment).last()
        StockMovement.objects.filter(pk=invalid.pk).update(movement_type=MovementType.PURCHASE)
        self.assertEqual(self.originals(adjustment).count(), 1)
        self.assert_cancel_rejected(adjustment, before_any_reverse=True)

    def test_wrong_content_type_cannot_disappear_from_actual_set(self):
        adjustment = self.make_adjustment(two=True)
        invalid = self.originals(adjustment).last()
        StockMovement.objects.filter(pk=invalid.pk).update(
            content_type=ContentType.objects.get_for_model(Warehouse), object_id=self.warehouse.pk)
        self.assertEqual(self.originals(adjustment).count(), 1)
        self.assert_cancel_rejected(adjustment, before_any_reverse=True)

    def test_reverse_linked_adjustment_type_is_not_an_actual_original(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        other = self.make_adjustment("OUT")
        foreign_original = self.originals(other).get()
        linked = StockMovementReversalService.reverse(
            movement=foreign_original, reversal_type=MovementType.ADJUSTMENT_IN)
        # ORM-representable extra row matching CT/object/type, but NOT reverses=NULL.
        StockMovement.objects.filter(pk=linked.pk).update(object_id=adjustment.pk)
        self.assertEqual(set(self.originals(adjustment).values_list("pk", flat=True)), {original.pk})
        self.cancel(adjustment)
        self.assert_historical_reversal(original)
        self.assertFalse(linked.reversal_movements.exists())
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, "CANCELLED")

    def test_company_mismatch_rejects_even_with_valid_foreign_stock_context(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        company = self.make_company("C08-FOREIGN")
        branch = Branch.objects.create(company=company, code="001", name="Foreign")
        warehouse = Warehouse.objects.create(company=company, branch=branch, code="W", name="Foreign")
        product = Product.objects.create(company=company, code="P", name="Foreign")
        Stock.objects.create(company=company, branch=branch, warehouse=warehouse, product=product,
                             quantity=Decimal("100"))
        # Internally valid movement context; mismatch is specifically with its document.
        StockMovement.objects.filter(pk=original.pk).update(
            company=company, branch=branch, warehouse=warehouse, product=product)
        self.assert_cancel_rejected(adjustment, before_any_reverse=True)

    def test_branch_mismatch_rejects_even_with_valid_same_company_stock_context(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        branch = Branch.objects.create(company=self.company, code="002", name="Other")
        warehouse = Warehouse.objects.create(company=self.company, branch=branch, code="W", name="Other")
        Stock.objects.create(company=self.company, branch=branch, warehouse=warehouse,
                             product=self.product, quantity=Decimal("100"))
        StockMovement.objects.filter(pk=original.pk).update(branch=branch, warehouse=warehouse)
        self.assert_cancel_rejected(adjustment, before_any_reverse=True)

    def test_original_with_prior_reversal_cannot_be_compensated_again(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        reversal = StockMovementReversalService.reverse(
            movement=original, reversal_type=MovementType.RETURN_OUT)
        self.assert_cancel_rejected(adjustment)
        self.assertEqual(list(original.reversal_movements.values_list("pk", flat=True)), [reversal.pk])

    def test_validate_all_before_reversing_any_original(self):
        adjustment = self.make_adjustment(two=True)
        originals = list(self.originals(adjustment).order_by("product_id", "pk"))
        self.assertEqual(len(originals), 2)
        # Quantity has no positive CHECK: this ORM corruption is representable.
        # The valid first movement must not be reversed before rejecting the second.
        StockMovement.objects.filter(pk=originals[1].pk).update(quantity=Decimal("0"))
        before_ids = set(StockMovement.objects.filter(reverses__in=originals).values_list("pk", flat=True))
        self.assert_cancel_rejected(adjustment, before_any_reverse=True)
        after_ids = set(StockMovement.objects.filter(reverses__in=originals).values_list("pk", flat=True))
        self.assertEqual(after_ids, before_ids)
        self.assertFalse(originals[0].reversal_movements.exists())
        self.assertFalse(originals[1].reversal_movements.exists())


class AdjustmentMovementHistoryTests(AdjustmentManifestFixture):
    def cancel_and_check(self, adjustment, original):
        self.cancel(adjustment)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, "CANCELLED")
        return self.assert_historical_reversal(original)

    def test_detail_product_mutation_does_not_change_reversal_product(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        adjustment.details.update(product=self.second_product)
        self.assertEqual(adjustment.details.get().product_id, self.second_product.pk)
        self.cancel_and_check(adjustment, original)
        self.assertEqual(Stock.objects.get(warehouse=self.warehouse, product=self.product).quantity, Decimal("100"))
        self.assertEqual(Stock.objects.get(warehouse=self.warehouse, product=self.second_product).quantity, Decimal("100"))

    def test_detail_quantity_mutation_does_not_change_reversal_quantity(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        adjustment.details.update(quantity=Decimal("91"))
        self.assertEqual(adjustment.details.get().quantity, Decimal("91"))
        self.cancel_and_check(adjustment, original)
        self.assertEqual(Stock.objects.get(warehouse=self.warehouse, product=self.product).quantity, Decimal("100"))

    def test_deleted_details_do_not_erase_operational_history(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        adjustment.details.all().delete()
        self.assertFalse(adjustment.details.exists())
        self.cancel_and_check(adjustment, original)

    def test_current_document_warehouse_does_not_replace_historical_warehouse(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        other = Warehouse.objects.create(company=self.company, branch=self.branch, code="W2", name="Other")
        Stock.objects.create(company=self.company, branch=self.branch, warehouse=other,
                             product=self.product, quantity=Decimal("100"))
        self.Adjustment.objects.filter(pk=adjustment.pk).update(warehouse=other)
        self.cancel_and_check(adjustment, original)
        self.assertEqual(Stock.objects.get(warehouse=other, product=self.product).quantity, Decimal("100"))
        self.assertEqual(Stock.objects.get(warehouse=self.warehouse, product=self.product).quantity, Decimal("100"))

    def test_reversal_preserves_original_unit_cost(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        # Legal stored history; no cost field exists on the adjustment detail.
        StockMovement.objects.filter(pk=original.pk).update(unit_cost=Decimal("7.123456"))
        self.cancel_and_check(adjustment, original)

    def test_current_document_type_behavior_does_not_determine_history(self):
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        # OUT is a declared choice; affects_inventory=True satisfies the CHECK.
        # TestCase rolls the catalog edit back; no shared/global data is changed.
        DocumentType.objects.filter(pk=adjustment.document_type_id).update(inventory_behavior="OUT")
        adjustment.document_type.refresh_from_db()
        adjustment.document_type.full_clean()
        self.cancel_and_check(adjustment, original)


class AdjustmentMovementReversalTests(AdjustmentManifestFixture):
    def assert_original_membership_survives(self, direction):
        adjustment = self.make_adjustment(direction, two=True)
        originals = list(self.originals(adjustment))
        expected_ids = {movement.pk for movement in originals}
        self.cancel(adjustment)
        reversals = [self.assert_historical_reversal(movement) for movement in originals]
        self.assertEqual(self.manifest_ids(adjustment), expected_ids)
        self.assertEqual(adjustment.movement_manifest.count(), 2)
        self.assertFalse(self.require_manifest_model().objects.filter(stock_movement__in=reversals).exists())
        self.assertEqual(self.movements(adjustment).count(), 4)

    def test_in_reverses_to_return_out_and_keeps_only_original_membership(self):
        self.assert_original_membership_survives("IN")

    def test_out_reverses_to_return_in_and_keeps_only_original_membership(self):
        self.assert_original_membership_survives("OUT")
