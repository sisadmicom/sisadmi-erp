from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from .sales_return_manifest_test_support import SalesReturnManifestFixture


class SalesReturnMovementIntegrityTests(SalesReturnManifestFixture):
    def test_manifest_expected_and_actual_ids_are_exact_sets(self):
        model = self.require_model()
        ret = self.confirm_return()
        expected = set(model.objects.filter(sales_return=ret).values_list("stock_movement_id", flat=True))
        actual = set(self.originals(ret).values_list("pk", flat=True))
        self.assertEqual(expected, actual)

    def test_company_and_branch_context_are_validated(self):
        model = self.require_model()
        ret = self.confirm_return()
        movement = self.originals(ret).get()
        self.assertEqual(movement.company_id, ret.company_id)
        self.assertEqual(movement.branch_id, ret.branch_id)

    def test_prior_reversal_is_rejected_without_double_compensation(self):
        model = self.require_model()
        ret = self.confirm_return()
        original = self.originals(ret).get()
        self.assertIsNone(original.reverses_id)
        self.assertEqual(model.objects.filter(sales_return=ret).count(), 1)

    def test_sales_return_confirmation_has_no_detail_to_movement_mapping(self):
        model = self.require_model()
        ret = self.confirm_return()
        self.assertFalse(any(field.name == "sales_return_detail" for field in model._meta.get_fields()))
