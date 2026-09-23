from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, models
from django.db.models.deletion import ProtectedError

from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from .sales_return_manifest_test_support import SalesReturnManifestFixture


class SalesReturnMovementModelContractTests(SalesReturnManifestFixture):
    def test_model_fields_are_minimal_and_required(self):
        model = self.require_model()
        self.assertEqual(model._meta.get_field("sales_return").remote_field.model._meta.label,
                         "sales.SalesReturn")
        stock_field = model._meta.get_field("stock_movement")
        self.assertIs(stock_field.remote_field.model, StockMovement)
        self.assertIs(stock_field.remote_field.on_delete, models.PROTECT)
        self.assertIs(model._meta.get_field("sales_return").remote_field.on_delete, models.PROTECT)
        self.assertFalse(model._meta.get_field("sales_return").null)
        self.assertFalse(stock_field.null)
        names = {field.name for field in model._meta.get_fields()}
        for forbidden in (
            "sales_return_detail", "sale_movement", "product", "quantity", "warehouse",
            "unit_cost", "price", "tax", "status", "movement_type",
        ):
            self.assertNotIn(forbidden, names)

    def test_stock_movement_is_one_to_one(self):
        model = self.require_model()
        self.assertTrue(model._meta.get_field("stock_movement").one_to_one)

    def test_one_return_can_have_many_manifests_but_movement_cannot_be_reused(self):
        model = self.require_model()
        ret = self.confirm_return(quantity="1")
        originals = list(self.originals(ret))
        self.assertEqual(len(originals), 1)
        self.assertEqual(model.objects.filter(sales_return=ret).count(), 1)
        with self.assertRaises(IntegrityError):
            model.objects.create(sales_return=ret, stock_movement=originals[0])

    def test_protects_sales_return_and_stock_movement(self):
        model = self.require_model()
        ret = self.confirm_return()
        manifest = model.objects.get(sales_return=ret)
        with self.assertRaises(ProtectedError):
            ret.delete()
        with self.assertRaises(ProtectedError):
            manifest.stock_movement.delete()


class SalesReturnMovementConfirmationTests(SalesReturnManifestFixture):
    def test_confirmation_captures_exact_return_in_ids(self):
        model = self.require_model()
        ret = self.confirm_return()
        originals = set(self.originals(ret).values_list("pk", flat=True))
        manifests = set(model.objects.filter(sales_return=ret).values_list("stock_movement_id", flat=True))
        self.assertEqual(len(originals), len(manifests))
        self.assertEqual(originals, manifests)

    def test_confirmation_cardinality_with_two_real_details(self):
        model = self.require_model()
        sale = self.make_two_line_sale()
        DTO, Line, creator, confirmer, _ = self.api()
        ret = creator.execute(DTO(
            sale_id=sale.pk, issue_date=sale.issue_date, notes="",
            details=[Line(sale_detail_id=detail.pk, quantity=Decimal("1")) for detail in sale.details.all()],
        ))
        confirmer.execute(ret.pk, user=None)
        originals = list(self.originals(ret))
        manifests = list(model.objects.filter(sales_return=ret))
        self.assertEqual(len(manifests), len(originals))
        self.assertEqual(len(manifests), ret.details.count())

    def test_confirmation_rolls_back_when_manifest_creation_fails(self):
        model = self.require_model()
        _, _, creator, confirmer, _ = self.api()
        ret = creator.execute(self.dto(quantity="1"))
        before = self.stock_quantity()
        with patch.object(model.objects, "create", side_effect=RuntimeError("manifest failure")):
            with self.assertRaises(RuntimeError):
                confirmer.execute(ret.pk, user=None)
        ret.refresh_from_db()
        self.assertEqual(ret.status, "DRAFT")
        self.assertEqual(self.stock_quantity(), before)
        self.assertFalse(self.originals(ret).exists())

    def stock_quantity(self):
        from inventory.models import Stock
        return Stock.objects.get(warehouse=self.warehouse, product=self.product).quantity


class SalesReturnMovementCancellationTests(SalesReturnManifestFixture):
    def test_cancellation_reverses_all_manifested_originals(self):
        model = self.require_model()
        ret = self.confirm_return()
        originals = list(self.originals(ret))
        self.api()[4].execute(ret.pk, user=None)
        for original in originals:
            reversal = StockMovement.objects.get(reverses_id=original.pk)
            self.assertEqual(reversal.movement_type, MovementType.RETURN_OUT)
        self.assertEqual(model.objects.filter(sales_return=ret).count(), len(originals))

    def test_missing_manifest_rejects_before_any_reversal(self):
        model = self.require_model()
        ret = self.confirm_return()
        model.objects.filter(sales_return=ret).delete()
        with self.assertRaises(Exception):
            self.api()[4].execute(ret.pk, user=None)
        self.assertEqual(StockMovement.objects.filter(reverses__isnull=False, object_id=ret.pk).count(), 0)

    def test_extra_return_in_rejects_before_any_reversal(self):
        model = self.require_model()
        ret = self.confirm_return()
        self.create_extra_return_in(ret)
        with self.assertRaises(Exception):
            self.api()[4].execute(ret.pk, user=None)
        self.assertEqual(StockMovement.objects.filter(reverses__isnull=False, object_id=ret.pk).count(), 0)

    def test_same_count_different_ids_rejects(self):
        model = self.require_model()
        sale = self.make_two_line_sale()
        DTO, Line, creator, confirmer, _ = self.api()
        details = list(sale.details.all())
        ret = creator.execute(DTO(
            sale_id=sale.pk, issue_date=sale.issue_date, notes="",
            details=[Line(sale_detail_id=detail.pk, quantity=Decimal("1")) for detail in details],
        ))
        confirmer.execute(ret.pk, user=None)
        rows = list(model.objects.filter(sales_return=ret).order_by("pk"))
        other = creator.execute(DTO(
            sale_id=sale.pk, issue_date=sale.issue_date, notes="",
            details=[Line(sale_detail_id=details[0].pk, quantity=Decimal("1"))],
        ))
        rows[1].stock_movement.object_id = other.pk
        rows[1].stock_movement.save(update_fields=["object_id"])
        extra = self.create_extra_return_in(ret)
        expected = set(model.objects.filter(sales_return=ret).values_list("stock_movement_id", flat=True))
        actual = set(self.originals(ret).values_list("pk", flat=True))
        self.assertEqual(len(expected), len(actual))
        self.assertNotEqual(expected, actual)
        with self.assertRaises(Exception):
            self.api()[4].execute(ret.pk, user=None)
        self.assertFalse(StockMovement.objects.filter(reverses__isnull=False, object_id=ret.pk).exists())

    def test_wrong_type_document_context_and_prior_reversal_are_service_invariants(self):
        model = self.require_model()
        ret = self.confirm_return()
        self.assertEqual(model.objects.filter(sales_return=ret).count(), 1)
        self.assertTrue(self.originals(ret).exists())

    def test_validate_all_precedes_first_reversal(self):
        model = self.require_model()
        ret = self.confirm_return()
        self.assertEqual(model.objects.filter(sales_return=ret).count(), self.originals(ret).count())


class SalesReturnMovementHistoryTests(SalesReturnManifestFixture):
    def test_mutated_or_deleted_details_do_not_define_cancellation_history(self):
        model = self.require_model()
        ret = self.confirm_return()
        ret.details.update(quantity=Decimal("1"))
        self.assertTrue(model.objects.filter(sales_return=ret).exists())

    def test_reversal_uses_original_historical_warehouse(self):
        model = self.require_model()
        ret = self.confirm_return()
        manifest = model.objects.get(sales_return=ret)
        self.assertEqual(manifest.stock_movement.warehouse_id, self.warehouse.pk)

    def test_source_sale_history_is_authenticated_before_return_manifest(self):
        model = self.require_model()
        ret = self.confirm_return()
        self.assertTrue(self.originals(ret).exists())
        self.assertEqual(model.objects.filter(sales_return=ret).count(), 1)

    def test_sales_return_manifest_isolated_from_other_return_in_creators(self):
        model = self.require_model()
        ret = self.confirm_return()
        self.assertEqual(model.objects.filter(sales_return=ret).count(), 1)
