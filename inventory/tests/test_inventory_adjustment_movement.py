"""C-08 schema, exact capture and transaction contracts (deliberately RED)."""
from unittest.mock import patch

from django.db import IntegrityError, connection, models, transaction
from django.db.models.deletion import ProtectedError

from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.stock import IncreaseStock, DecreaseStock
from inventory.tests.adjustment_manifest_test_support import AdjustmentManifestFixture


class AdjustmentMovementSchemaTests(AdjustmentManifestFixture):
    def test_only_identity_and_two_required_protected_relations(self):
        model = self.require_manifest_model()
        self.assertEqual({f.name for f in model._meta.local_fields},
                         {"id", "inventory_adjustment", "stock_movement"})
        adjustment_field = model._meta.get_field("inventory_adjustment")
        stock_field = model._meta.get_field("stock_movement")
        self.assertIsInstance(adjustment_field, models.ForeignKey)
        self.assertFalse(adjustment_field.one_to_one)
        self.assertIs(adjustment_field.remote_field.model, self.Adjustment)
        self.assertEqual(adjustment_field.remote_field.related_name, "movement_manifest")
        self.assertIsInstance(stock_field, models.OneToOneField)
        self.assertIs(stock_field.remote_field.model, StockMovement)
        self.assertEqual(stock_field.remote_field.related_name, "inventory_adjustment_movement_manifest")
        for field in (adjustment_field, stock_field):
            self.assertFalse(field.null)
            self.assertFalse(field.blank)
            self.assertIs(field.remote_field.on_delete, models.PROTECT)
        self.assertFalse(any(isinstance(c, models.UniqueConstraint) and c.fields == ("stock_movement",)
                             for c in model._meta.constraints))

    def test_inventory_adjustment_is_required_by_database(self):
        model = self.require_manifest_model()
        adjustment = self.make_adjustment()
        original = self.originals(adjustment).get()
        model.objects.filter(inventory_adjustment=adjustment).delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.create(stock_movement=original)

    def test_stock_movement_is_required_by_database(self):
        model = self.require_manifest_model()
        adjustment = self.make_adjustment(confirmed=False)
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.create(inventory_adjustment=adjustment)

    def test_movement_cannot_belong_to_two_adjustments(self):
        model = self.require_manifest_model()
        adjustment = self.make_adjustment()
        other = self.make_adjustment(confirmed=False)
        original = self.originals(adjustment).get()
        self.assertEqual(self.manifest_ids(adjustment), {original.pk})
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.create(inventory_adjustment=other, stock_movement=original)

    def test_manifest_protects_adjustment(self):
        model = self.require_manifest_model()
        adjustment = self.make_adjustment()
        manifest = model.objects.get(inventory_adjustment=adjustment)
        with self.assertRaises(ProtectedError) as error:
            adjustment.delete()
        self.assertIn(manifest, error.exception.protected_objects)

    def test_manifest_protects_original_movement(self):
        model = self.require_manifest_model()
        adjustment = self.make_adjustment()
        manifest = model.objects.get(inventory_adjustment=adjustment)
        with self.assertRaises(ProtectedError) as error:
            manifest.stock_movement.delete()
        self.assertIn(manifest, error.exception.protected_objects)

    def test_manifest_survives_detail_deletion_without_detail_relation(self):
        model = self.require_manifest_model()
        adjustment = self.make_adjustment()
        before = list(model.objects.filter(inventory_adjustment=adjustment).values())
        self.assertEqual(len(before), 1)
        adjustment.details.all().delete()
        self.assertFalse(adjustment.details.exists())
        self.assertEqual(list(model.objects.filter(inventory_adjustment=adjustment).values()), before)


class AdjustmentMovementConfirmationTests(AdjustmentManifestFixture):
    def assert_exact_capture(self, direction, *, preexisting_effect=False):
        adjustment = self.make_adjustment(direction, two=True, confirmed=False)
        if preexisting_effect:
            # A legal stock effect already references this draft. It must never be
            # adopted by product/quantity/order when capturing newly returned IDs.
            IncreaseStock().execute(
                company=self.company, branch=self.branch, warehouse=self.warehouse,
                product=self.product, quantity=adjustment.details.get(product=self.product).quantity,
                movement_type=MovementType.ADJUSTMENT_IN, document=adjustment, return_movement=True)
        preexisting_ids = set(self.originals(adjustment).values_list("pk", flat=True))
        service = IncreaseStock if direction == "IN" else DecreaseStock
        execute = service.execute
        returned_ids = []

        def observe(instance, **kwargs):
            self.assertTrue(kwargs.get("return_movement"),
                            "C-08 missing manifest capture: request the exact StockMovement")
            self.assertTrue(connection.in_atomic_block)
            # Before the next effect, the preceding returned ID must already be captured.
            if returned_ids:
                self.assertEqual(self.manifest_ids(adjustment), set(returned_ids))
            movement = execute(instance, **kwargs)
            self.assertIsInstance(movement, StockMovement)
            returned_ids.append(movement.pk)
            return movement

        with patch.object(service, "execute", autospec=True, side_effect=observe):
            self.confirm(adjustment)
        actual = set(self.originals(adjustment).values_list("pk", flat=True)) - preexisting_ids
        self.assertEqual(len(returned_ids), 2)
        self.assertEqual(adjustment.details.count(), 2)
        self.assertEqual(len(actual), 2)
        self.assertEqual(actual, set(returned_ids))
        self.assertEqual(self.manifest_ids(adjustment), set(returned_ids))
        self.assertEqual(adjustment.movement_manifest.count(), 2)

    def test_in_captures_exact_returned_ids_before_next_effect(self):
        self.assert_exact_capture("IN")

    def test_out_captures_exact_returned_ids_before_next_effect(self):
        self.assert_exact_capture("OUT")

    def test_confirmation_does_not_adopt_preexisting_identical_history(self):
        self.assert_exact_capture("IN", preexisting_effect=True)

    def test_second_manifest_failure_rolls_back_document_stock_history_and_manifest(self):
        model = self.require_manifest_model()
        adjustment = self.make_adjustment(two=True, confirmed=False)
        before = self.state(adjustment)
        create = model.objects.create
        calls = []

        def fail_second(**kwargs):
            self.assertTrue(connection.in_atomic_block)
            calls.append(kwargs)
            if len(calls) == 2:
                self.assertEqual(self.originals(adjustment).count(), 2)
                self.assertEqual(model.objects.filter(inventory_adjustment=adjustment).count(), 1)
                raise IntegrityError("C08 injected second manifest persistence failure")
            return create(**kwargs)

        with patch.object(model.objects, "create", side_effect=fail_second):
            with self.assertRaisesRegex(IntegrityError, "C08 injected second manifest"):
                self.confirm(adjustment)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.state(adjustment), before)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, "DRAFT")
        self.assertFalse(self.originals(adjustment).exists())
        self.assertFalse(model.objects.filter(inventory_adjustment=adjustment).exists())
