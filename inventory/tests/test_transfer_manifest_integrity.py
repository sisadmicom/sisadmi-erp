from decimal import Decimal
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.test import TestCase

from core.models import Branch, Company
from people.models import Person
from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from inventory.tests.transfer_manifest_test_support import TransferManifestFixture
from inventory.use_cases.cancel_transfer import CancelTransfer


class TransferManifestCancellationContractTest(TransferManifestFixture, TestCase):
    def test_CA1_to_CA7_valid_manifest_reverses_originals_only(self):
        transfer = self.confirmed_transfer()
        pair_model = self.pair_model()
        pair = pair_model.objects.get(transfer=transfer)
        originals = list(self.original_movements(transfer))
        CancelTransfer.execute(transfer_id=transfer.pk, user=None)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "CANCELLED")
        for original in originals:
            reversal = original.reversal_movements.get()
            expected = MovementType.RETURN_IN if original.movement_type == MovementType.TRANSFER_OUT else MovementType.RETURN_OUT
            self.assertEqual(reversal.movement_type, expected)
            self.assertEqual(reversal.reverses_id, original.pk)
        pair.refresh_from_db()
        self.assertEqual({pair.out_movement_id, pair.in_movement_id}, {m.pk for m in originals})
        self.assertFalse(pair_model.objects.filter(out_movement__reverses__isnull=False).exists())

    def _corrupt_and_reject(self, mutate):
        transfer = self.confirmed_transfer()
        pair = self.pair_model().objects.get(transfer=transfer)
        mutate(transfer, pair)
        self.cancel_and_expect_rejection(transfer)

    def test_SE1_schema_prevents_deleting_referenced_original(self):
        transfer, pair = self.confirmed_pair()
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):
            pair.out_movement.delete()

    def test_SE2_extra_original_rejected(self):
        def mutate(transfer, pair):
            StockMovement.objects.create(
                company=self.company, branch=self.branch, warehouse=self.source_warehouse,
                product=self.product, movement_type=MovementType.TRANSFER_OUT,
                quantity=Decimal("5"), content_type=ContentType.objects.get_for_model(transfer),
                object_id=transfer.pk,
            )
        self._corrupt_and_reject(mutate)

    def test_SE3_missing_pair_rejected(self):
        def mutate(transfer, pair):
            pair.delete()
        self._corrupt_and_reject(mutate)

    def test_SE4_schema_prevents_duplicate_one_to_one_pair(self):
        transfer, pair = self.confirmed_pair()
        with self.assertRaises(IntegrityError):
            self.pair_model().objects.create(
                transfer=transfer, out_movement=pair.out_movement,
                in_movement=pair.in_movement,
            )

    def test_SE5_same_count_different_id_rejected(self):
        transfer = self.confirmed_transfer()
        pair = self.pair_model().objects.get(transfer=transfer)
        other_transfer = self.create_transfer("1")
        replacement = StockMovement.objects.create(
            company=self.company, branch=self.branch, warehouse=self.source_warehouse,
            product=self.product, movement_type=MovementType.TRANSFER_OUT,
            quantity=Decimal("5"), content_type=ContentType.objects.get_for_model(transfer),
            object_id=transfer.pk,
        )
        StockMovement.objects.filter(pk=pair.out_movement_id).update(object_id=other_transfer.pk)
        pair.refresh_from_db()
        self.assertEqual(self.original_movements(transfer).count(), 2)
        self.assertNotEqual(pair.out_movement_id, replacement.pk)
        self.cancel_and_expect_rejection(transfer)

    def test_SE6_equivalent_attribute_substitution_rejected(self):
        self.test_SE5_same_count_different_id_rejected()

    def _mutate_and_reject(self, field, value):
        transfer, pair = self.confirmed_pair()
        StockMovement.objects.filter(pk=pair.out_movement_id).update(**{field: value})
        self.cancel_and_expect_rejection(transfer)

    def test_PV2_wrong_out_type(self):
        self._mutate_and_reject("movement_type", MovementType.ADJUSTMENT_OUT)

    def test_PV3_wrong_in_type(self):
        transfer, pair = self.confirmed_pair()
        StockMovement.objects.filter(pk=pair.in_movement_id).update(movement_type=MovementType.ADJUSTMENT_IN)
        self.cancel_and_expect_rejection(transfer)

    def test_PV4_wrong_out_document(self):
        transfer, pair = self.confirmed_pair()
        other = self.create_transfer("1")
        StockMovement.objects.filter(pk=pair.out_movement_id).update(object_id=other.pk)
        self.cancel_and_expect_rejection(transfer)

    def test_PV5_wrong_in_document(self):
        transfer, pair = self.confirmed_pair()
        other = self.create_transfer("1")
        StockMovement.objects.filter(pk=pair.in_movement_id).update(object_id=other.pk)
        self.cancel_and_expect_rejection(transfer)

    def test_PV6_product_mismatch(self):
        transfer, pair = self.confirmed_pair()
        product = self.add_second_product()
        StockMovement.objects.filter(pk=pair.in_movement_id).update(product_id=product.pk)
        self.cancel_and_expect_rejection(transfer)

    def test_PV7_quantity_mismatch(self):
        transfer, pair = self.confirmed_pair()
        StockMovement.objects.filter(pk=pair.in_movement_id).update(quantity=Decimal("4"))
        self.cancel_and_expect_rejection(transfer)

    def test_PV8_same_warehouse(self):
        transfer, pair = self.confirmed_pair()
        StockMovement.objects.filter(pk=pair.in_movement_id).update(warehouse_id=self.source_warehouse.pk)
        self.cancel_and_expect_rejection(transfer)

    def test_PV9_company_mismatch(self):
        transfer, pair = self.confirmed_pair()
        person = Person.objects.create(identification="1790000001002", person_type="LEGAL", full_name="Otra empresa")
        other_company = Company.objects.create(person=person, commercial_name="Otra")
        StockMovement.objects.filter(pk=pair.in_movement_id).update(company_id=other_company.pk)
        self.cancel_and_expect_rejection(transfer)

    def test_PV10_branch_mismatch(self):
        transfer, pair = self.confirmed_pair()
        other_branch = Branch.objects.create(company=self.company, code="002", name="Otra")
        StockMovement.objects.filter(pk=pair.in_movement_id).update(branch_id=other_branch.pk)
        self.cancel_and_expect_rejection(transfer)

    def test_PV11_unit_cost_mismatch(self):
        transfer, pair = self.confirmed_pair()
        StockMovement.objects.filter(pk=pair.in_movement_id).update(unit_cost=Decimal("1"))
        self.cancel_and_expect_rejection(transfer)

    def test_PV12_original_already_reversed(self):
        transfer, pair = self.confirmed_pair()
        StockMovementReversalService.reverse(
            movement=pair.out_movement, reversal_type=MovementType.RETURN_IN,
        )
        before_ids = set(self.document_movements(transfer).filter(reverses__isnull=False).values_list("pk", flat=True))
        with self.assertRaises(Exception):
            CancelTransfer.execute(transfer_id=transfer.pk, user=None)
        after_ids = set(self.document_movements(transfer).filter(reverses__isnull=False).values_list("pk", flat=True))
        self.assertEqual(after_ids, before_ids)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "CONFIRMED")

    def test_PV13_manifest_points_to_reversal(self):
        transfer, pair = self.confirmed_pair()
        StockMovementReversalService.reverse(
            movement=pair.out_movement, reversal_type=MovementType.RETURN_IN,
        )
        reversal = pair.out_movement.reversal_movements.get()
        pair.out_movement = reversal
        pair.save(update_fields=["out_movement"])
        before_ids = set(self.document_movements(transfer).filter(reverses__isnull=False).values_list("pk", flat=True))
        with self.assertRaises(Exception):
            CancelTransfer.execute(transfer_id=transfer.pk, user=None)
        after_ids = set(self.document_movements(transfer).filter(reverses__isnull=False).values_list("pk", flat=True))
        self.assertEqual(after_ids, before_ids)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "CONFIRMED")

    def _cross_role_reuse(self, reuse_out_as_in):
        transfer1 = self.confirmed_transfer()
        transfer2 = self.confirmed_transfer()
        pair1 = self.pair_model().objects.get(transfer=transfer1)
        pair2 = self.pair_model().objects.get(transfer=transfer2)
        if reuse_out_as_in:
            pair2.in_movement = pair1.out_movement
        else:
            pair2.out_movement = pair1.in_movement
        pair2.save(update_fields=["in_movement" if reuse_out_as_in else "out_movement"])
        self.cancel_and_expect_rejection(transfer2)

    def test_UX1_out_of_pair1_reused_as_in_of_pair2_rejected(self):
        self._cross_role_reuse(True)

    def test_UX2_in_of_pair1_reused_as_out_of_pair2_rejected(self):
        self._cross_role_reuse(False)

    def test_UX3_cross_role_corruption_has_no_partial_reversal(self):
        transfer1 = self.confirmed_transfer()
        transfer2 = self.confirmed_transfer()
        pair1 = self.pair_model().objects.get(transfer=transfer1)
        pair2 = self.pair_model().objects.get(transfer=transfer2)
        pair2.in_movement = pair1.out_movement
        pair2.save(update_fields=["in_movement"])
        self.cancel_and_expect_rejection(transfer2)

    def test_RC1_validation_failure_precedes_all_reversals(self):
        transfer = self.confirmed_two_line_transfer()
        pair = self.pair_model().objects.filter(transfer=transfer).order_by("pk").last()
        StockMovement.objects.filter(pk=pair.in_movement_id).update(quantity=Decimal("4"))
        self.cancel_and_expect_rejection(transfer)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "CONFIRMED")

    def test_RC2_late_reversal_failure_rolls_back_all_reversals(self):
        transfer = self.confirmed_two_line_transfer()
        original = StockMovementReversalService.reverse
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("C-04 reversal failure")
            return original(*args, **kwargs)
        with patch.object(StockMovementReversalService, "reverse", side_effect=fail_second):
            with self.assertRaisesMessage(RuntimeError, "C-04 reversal failure"):
                CancelTransfer.execute(transfer_id=transfer.pk, user=None)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "CONFIRMED")
        self.assertFalse(self.document_movements(transfer).filter(reverses__isnull=False).exists())

    def test_RC3_document_cancel_is_last_operation(self):
        transfer = self.confirmed_transfer()
        original = DocumentService.cancel
        observed = {}
        def cancel_last(document, user=None):
            original_ids = set(self.document_movements(document).filter(reverses__isnull=True).values_list("pk", flat=True))
            reversed_ids = set(self.document_movements(document).filter(reverses_id__in=original_ids).values_list("reverses_id", flat=True))
            observed["all_reversed"] = reversed_ids == original_ids
            return original(document, user=user)
        with patch.object(DocumentService, "cancel", side_effect=cancel_last):
            CancelTransfer.execute(transfer_id=transfer.pk, user=None)
        self.assertTrue(observed["all_reversed"])
