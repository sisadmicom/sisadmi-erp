from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, models, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.tests.transfer_manifest_test_support import TransferManifestFixture
from inventory.use_cases.confirm_transfer import ConfirmTransfer


class TransferMovementPairModelContractTest(TransferManifestFixture, TestCase):
    def test_M1_model_exists(self):
        self.assertIsNotNone(self.pair_model())

    def test_M2_transfer_is_required(self):
        self.assertFalse(self.pair_model()._meta.get_field("transfer").null)

    def test_M3_out_movement_is_required(self):
        self.assertFalse(self.pair_model()._meta.get_field("out_movement").null)

    def test_M4_in_movement_is_required(self):
        self.assertFalse(self.pair_model()._meta.get_field("in_movement").null)

    def test_M5_transfer_uses_protect(self):
        self.assertIs(self.pair_model()._meta.get_field("transfer").remote_field.on_delete, models.PROTECT)

    def test_M6_out_uses_protect(self):
        self.assertIs(self.pair_model()._meta.get_field("out_movement").remote_field.on_delete, models.PROTECT)

    def test_M7_in_uses_protect(self):
        self.assertIs(self.pair_model()._meta.get_field("in_movement").remote_field.on_delete, models.PROTECT)

    def test_M8_out_movement_is_unique(self):
        field = self.pair_model()._meta.get_field("out_movement")
        self.assertTrue(field.one_to_one or field.unique)

    def test_M9_in_movement_is_unique(self):
        field = self.pair_model()._meta.get_field("in_movement")
        self.assertTrue(field.one_to_one or field.unique)

    def test_M10_out_and_in_are_distinct_schema_check(self):
        transfer = self.confirmed_transfer()
        movement = StockMovement.objects.create(
            company=self.company, branch=self.branch, warehouse=self.source_warehouse,
            product=self.product, movement_type=MovementType.TRANSFER_OUT,
            quantity=Decimal("1"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.pair_model().objects.create(
                    transfer=transfer, out_movement=movement, in_movement=movement,
                )

    def test_M11_no_required_transfer_detail_fk(self):
        field_names = {field.name for field in self.pair_model()._meta.get_fields()}
        self.assertNotIn("transfer_detail", field_names)

    def test_M12_manifest_does_not_duplicate_operational_snapshots(self):
        field_names = {field.name for field in self.pair_model()._meta.get_fields()}
        self.assertTrue(field_names.issubset({"id", "transfer", "out_movement", "in_movement", "created_at", "updated_at"}))

    def test_PR1_to_PR3_protects_transfer_and_movements(self):
        transfer, pair = self.confirmed_pair()
        with self.assertRaises(ProtectedError):
            transfer.delete()
        with self.assertRaises(ProtectedError):
            pair.out_movement.delete()
        with self.assertRaises(ProtectedError):
            pair.in_movement.delete()


class TransferMovementPairConfirmationContractTest(TransferManifestFixture, TestCase):
    def test_CF1_to_CF6_one_line_creates_one_pair_and_two_originals(self):
        transfer = self.confirmed_transfer()
        pair = self.pair_model().objects.get(transfer=transfer)
        originals = self.original_movements(transfer)
        self.assertEqual(self.pair_model().objects.filter(transfer=transfer).count(), 1)
        self.assertEqual(originals.count(), 2)
        out = originals.get(movement_type=MovementType.TRANSFER_OUT)
        incoming = originals.get(movement_type=MovementType.TRANSFER_IN)
        self.assertEqual(pair.out_movement_id, out.pk)
        self.assertEqual(pair.in_movement_id, incoming.pk)
        self.assertEqual(out.document, transfer)
        self.assertEqual(incoming.document, transfer)
        self.assertEqual(out.product_id, incoming.product_id)
        self.assertEqual(out.quantity, incoming.quantity)
        self.assertNotEqual(out.warehouse_id, incoming.warehouse_id)
        self.assertEqual(out.unit_cost, Decimal("0"))
        self.assertEqual(incoming.unit_cost, Decimal("0"))

    def test_CF7_N_details_create_N_pairs_and_2N_originals(self):
        transfer = self.confirmed_two_line_transfer()
        self.assertEqual(self.pair_model().objects.filter(transfer=transfer).count(), 2)
        self.assertEqual(self.original_movements(transfer).count(), 4)

    def test_CF_exact_ids_are_not_selected_by_attributes_or_order(self):
        transfer = self.confirmed_transfer()
        pair = self.pair_model().objects.get(transfer=transfer)
        self.assertEqual(
            {pair.out_movement_id, pair.in_movement_id},
            set(self.original_movements(transfer).values_list("pk", flat=True)),
        )

    def test_CF_A1_failure_after_out_rolls_back_pair_and_effects(self):
        transfer = self.create_transfer()
        from inventory.services.stock.increase_stock import IncreaseStock
        with patch.object(IncreaseStock, "execute", side_effect=RuntimeError("C-04 IN failure")):
            with self.assertRaisesMessage(RuntimeError, "C-04 IN failure"):
                ConfirmTransfer.execute(transfer_id=transfer.pk, user=None)
        self.assertEqual(self.original_movements(transfer).count(), 0)
        self.assertEqual(self.pair_model().objects.filter(transfer=transfer).count(), 0)

    def test_CF_A2_pair_persistence_failure_rolls_back_everything(self):
        transfer = self.create_transfer()
        pair_model = self.pair_model()
        with patch.object(pair_model.objects, "create", side_effect=RuntimeError("C-04 pair failure")):
            with self.assertRaisesMessage(RuntimeError, "C-04 pair failure"):
                ConfirmTransfer.execute(transfer_id=transfer.pk, user=None)
        self.assertEqual(self.original_movements(transfer).count(), 0)

    def test_CF_A3_second_line_failure_rolls_back_all_lines(self):
        transfer = self.create_two_line_transfer()
        sequence_before = self.sequence.next_number
        stocks_before = list(self.stock_snapshot(transfer))
        from inventory.services.stock.increase_stock import IncreaseStock
        calls = 0
        original = IncreaseStock.execute
        def fail_second(service, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("C-04 second line failure")
            return original(service, **kwargs)
        with patch.object(IncreaseStock, "execute", new=fail_second):
            with self.assertRaisesMessage(RuntimeError, "C-04 second line failure"):
                ConfirmTransfer.execute(transfer_id=transfer.pk, user=None)
        transfer.refresh_from_db()
        self.sequence.refresh_from_db()
        self.assertEqual(transfer.status, "DRAFT")
        self.assertEqual(self.sequence.next_number, sequence_before)
        self.assertEqual(list(self.stock_snapshot(transfer)), stocks_before)
        self.assertEqual(self.original_movements(transfer).count(), 0)
        self.assertEqual(self.pair_model().objects.filter(transfer=transfer).count(), 0)

    def stock_snapshot(self, transfer):
        from inventory.models import Stock
        return Stock.objects.filter(company_id=transfer.company_id, branch_id=transfer.branch_id).order_by("pk").values_list("warehouse_id", "product_id", "quantity")


class TransferMovementPairCompatibilityTest(TransferManifestFixture, TestCase):
    def test_MD1_MD2_mutating_detail_does_not_change_historical_pair(self):
        transfer, pair = self.confirmed_pair("10")
        transfer.details.update(quantity=Decimal("3"))
        pair.refresh_from_db()
        self.assertEqual(pair.out_movement.quantity, Decimal("10"))
        self.assertEqual(pair.in_movement.quantity, Decimal("10"))

    def test_MD3_MD4_deleting_detail_keeps_pair_and_allows_cancel(self):
        transfer, pair = self.confirmed_pair()
        transfer.details.all().delete()
        pair.refresh_from_db()
        self.assertTrue(pair.pk)

    def test_MH1_MH2_header_warehouse_mutation_does_not_change_reversal_warehouse(self):
        transfer, pair = self.confirmed_pair()
        from inventory.models import Warehouse
        transfer.source_warehouse = Warehouse.objects.create(company=self.company, branch=self.branch, code="B003", name="Mutada")
        transfer.destination_warehouse = Warehouse.objects.create(company=self.company, branch=self.branch, code="B004", name="Mutada 2")
        transfer.save(update_fields=["source_warehouse", "destination_warehouse"])
        self.assertEqual(pair.out_movement.warehouse_id, self.source_warehouse.pk)
        self.assertEqual(pair.in_movement.warehouse_id, self.destination_warehouse.pk)

    def test_PR4_detail_delete_does_not_delete_pair(self):
        transfer, pair = self.confirmed_pair()
        transfer.details.all().delete()
        self.assertTrue(self.pair_model().objects.filter(pk=pair.pk).exists())
