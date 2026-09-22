from decimal import Decimal
from unittest.mock import patch

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError

from core.constants.document_status import DocumentStatus
from core.models import Branch, DocumentType, Sequence
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from purchases.models import Purchase
from purchases.services.purchase_cancellation_service import PurchaseCancellationService
from purchases.services.purchase_return_confirmation_service import PurchaseReturnConfirmationService
from purchases.tests.purchase_manifest_test_support import PurchaseManifestFixture
from people.models import Person
from purchases.use_cases.cancel_purchase import CancelPurchase
from purchases.use_cases.create_purchase_return import CreatePurchaseReturn


class PurchaseMovementConfirmationTests(PurchaseManifestFixture):
    def test_single_purchase_creates_exact_manifest(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        originals = list(self.original_movements(purchase))
        rows = list(model.objects.filter(purchase=purchase))
        self.assertEqual(len(originals), 1)
        self.assertEqual([row.stock_movement_id for row in rows], [originals[0].pk])
        self.assertEqual(originals[0].movement_type, MovementType.PURCHASE)
        self.assertEqual(originals[0].document, purchase)

    def test_two_lines_create_two_distinct_manifest_rows(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase([
            (self.product, Decimal("5"), Decimal("10")),
            (self.product_2, Decimal("2"), Decimal("4")),
        ]))
        self.assertEqual(self.original_movements(purchase).count(), 2)
        self.assertEqual(model.objects.filter(purchase=purchase).count(), 2)
        self.assertEqual({r.stock_movement_id for r in model.objects.filter(purchase=purchase)}, {m.pk for m in self.original_movements(purchase)})

    def test_duplicate_products_keep_distinct_effect_identity(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase([
            (self.product, Decimal("5"), Decimal("10")),
            (self.product, Decimal("5"), Decimal("10")),
        ]))
        self.assertEqual(self.original_movements(purchase).count(), 2)
        self.assertEqual(model.objects.filter(purchase=purchase).values("stock_movement_id").distinct().count(), 2)

    def test_movement_snapshots_match_detail_at_confirmation(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase([(self.product, Decimal("5"), Decimal("12.50"))]))
        movement = self.original_movements(purchase).get()
        detail = purchase.details.get()
        self.assertEqual((movement.product_id, movement.quantity, movement.unit_cost), (detail.product_id, detail.quantity, detail.unit_price))
        self.assertEqual(model.objects.get(purchase=purchase).stock_movement_id, movement.pk)

    def test_zero_or_multiple_main_warehouses_reject_before_effects(self):
        for mode in ("zero", "multiple"):
            with self.subTest(mode=mode):
                purchase = self.make_purchase()
                Warehouse.objects.filter(pk=self.warehouse_a.pk).update(is_main=(mode == "multiple"))
                if mode == "multiple":
                    Warehouse.objects.filter(pk=self.warehouse_b.pk).update(is_main=True)
                before = self.stock_snapshot(purchase)
                with self.assertRaises(Exception):
                    self.confirm(purchase)
                purchase.refresh_from_db()
                self.assertEqual(purchase.status, DocumentStatus.DRAFT)
                self.assertEqual(purchase.number, "")
                self.assertEqual(self.stock_snapshot(purchase), before)
                self.assertFalse(self.original_movements(purchase).exists())

    def test_other_company_or_branch_main_is_not_selected(self):
        purchase = self.make_purchase()
        from people.models import Person
        other_company = self.company.__class__.objects.create(
            person=Person.objects.create(identification="1790000002002", person_type="LEGAL", full_name="Otra"),
            commercial_name="Otra",
        )
        # La única main ajena no satisface company/branch de Purchase.
        Warehouse.objects.filter(pk=self.warehouse_a.pk).update(is_main=False)
        Warehouse.objects.create(company=other_company, branch=self.branch, code="X", name="Ajena", is_main=True)
        with self.assertRaises(Exception):
            self.confirm(purchase)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, DocumentStatus.DRAFT)


class PurchaseMovementCancellationTests(PurchaseManifestFixture):
    def test_cancel_uses_historical_warehouse_after_main_changes(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        Warehouse.objects.filter(pk=self.warehouse_a.pk).update(is_main=False)
        Warehouse.objects.filter(pk=self.warehouse_b.pk).update(is_main=True)
        PurchaseCancellationService.cancel(purchase.pk)
        reversal = StockMovement.objects.get(reverses_id=self.original_movements(purchase).first().pk)
        self.assertEqual(reversal.warehouse_id, self.warehouse_a.pk)

    def test_detail_mutation_does_not_change_historical_cancellation(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        detail = purchase.details.get()
        detail.product = self.product_2
        detail.quantity = Decimal("1")
        detail.unit_price = Decimal("999")
        detail.save()
        PurchaseCancellationService.cancel(purchase.pk)
        self.assertEqual(StockMovement.objects.filter(reverses__isnull=False, object_id=purchase.pk).count(), 1)

    def test_detail_deletion_does_not_remove_manifest_or_block_cancel(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        movement_id = self.original_movements(purchase).get().pk
        purchase.details.all().delete()
        self.assertEqual(model.objects.filter(purchase=purchase).values_list("stock_movement_id", flat=True).get(), movement_id)
        PurchaseCancellationService.cancel(purchase.pk)
        self.assertEqual(Purchase.objects.get(pk=purchase.pk).status, DocumentStatus.CANCELLED)

    def test_exact_set_rejects_missing_manifest_row(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        model.objects.get(purchase=purchase).delete()
        with self.assertRaises(Exception):
            PurchaseCancellationService.cancel(purchase.pk)

    def test_exact_set_rejects_extra_purchase_movement(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        from inventory.services.movement.create_stock_movement import CreateStockMovement
        CreateStockMovement().execute(company=self.company, branch=self.branch, warehouse=self.warehouse_a,
                                      product=self.product, quantity=Decimal("1"), unit_cost=Decimal("10"),
                                      movement_type=MovementType.PURCHASE, document=purchase)
        with self.assertRaises(Exception):
            PurchaseCancellationService.cancel(purchase.pk)

    def test_semantic_corruption_is_rejected_before_reversal(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        movement = self.original_movements(purchase).get()
        before = self.stock_snapshot(purchase)
        other_company = self.company.__class__.objects.create(
            person=Person.objects.create(identification="1790000003003", person_type="LEGAL", full_name="Contexto alterno"),
            commercial_name="Contexto alterno",
        )
        other_branch = Branch.objects.create(company=other_company, code="ALT", name="Sucursal alterna")
        mutations = (
            {"movement_type": MovementType.SALE},
            {"object_id": 999999},
            {"company_id": other_company.pk},
            {"branch_id": other_branch.pk},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                StockMovement.objects.filter(pk=movement.pk).update(**mutation)
                with self.assertRaises(Exception):
                    PurchaseCancellationService.cancel(purchase.pk)
                self.assertEqual(self.stock_snapshot(purchase), before)
                StockMovement.objects.filter(pk=movement.pk).update(
                    movement_type=MovementType.PURCHASE, object_id=purchase.pk,
                    product_id=self.product.pk, quantity=Decimal("5"),
                    warehouse_id=self.warehouse_a.pk, company_id=self.company.pk,
                    branch_id=self.branch.pk, unit_cost=Decimal("10"),
                )

    def test_original_already_reversed_is_rejected_without_new_effect(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        original = self.original_movements(purchase).get()
        StockMovementReversalService.reverse(movement=original, reversal_type=MovementType.RETURN_OUT)
        before = set(StockMovement.objects.filter(reverses_id=original.pk).values_list("pk", flat=True))
        with self.assertRaises(Exception):
            PurchaseCancellationService.cancel(purchase.pk)
        self.assertEqual(set(StockMovement.objects.filter(reverses_id=original.pk).values_list("pk", flat=True)), before)
        self.assertEqual(Purchase.objects.get(pk=purchase.pk).status, DocumentStatus.CONFIRMED)

    def test_reversal_contract_and_manifest_survive_cancel(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        original = self.original_movements(purchase).get()
        PurchaseCancellationService.cancel(purchase.pk)
        reversal = StockMovement.objects.get(reverses_id=original.pk)
        self.assertIsNone(original.reverses_id)
        self.assertEqual(reversal.reverses_id, original.pk)
        self.assertEqual(model.objects.get(purchase=purchase).stock_movement_id, original.pk)
        self.assertEqual(model.objects.filter(stock_movement=reversal).count(), 0)

    def test_all_reversals_exist_before_document_cancel(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        original = list(self.original_movements(purchase))
        seen = {}
        from core.services.document_service import DocumentService
        real_cancel = DocumentService.cancel
        def check_then_cancel(document, user=None):
            self.assertEqual(set(StockMovement.objects.filter(reverses_id__in=[m.pk for m in original]).values_list("reverses_id", flat=True)), {m.pk for m in original})
            return real_cancel(document=document, user=user)
        with patch.object(DocumentService, "cancel", side_effect=check_then_cancel):
            PurchaseCancellationService.cancel(purchase.pk)
        self.assertEqual(Purchase.objects.get(pk=purchase.pk).status, DocumentStatus.CANCELLED)

    def test_late_reversal_failure_rolls_back(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase([
            (self.product, Decimal("5"), Decimal("10")),
            (self.product_2, Decimal("2"), Decimal("4")),
        ]))
        real = StockMovementReversalService.reverse
        calls = {"n": 0}
        def fail_second(*, movement, reversal_type, user=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("late reversal")
            return real(movement=movement, reversal_type=reversal_type, user=user)
        with patch.object(StockMovementReversalService, "reverse", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                PurchaseCancellationService.cancel(purchase.pk)
        self.assertEqual(Purchase.objects.get(pk=purchase.pk).status, DocumentStatus.CONFIRMED)
        self.assertFalse(StockMovement.objects.filter(object_id=purchase.pk, reverses__isnull=False).exists())


class PurchaseReturnManifestIntegrationTests(PurchaseManifestFixture):
    def make_return(self, purchase):
        from purchases.dto.purchase_return_create_dto import PurchaseReturnCreateDTO
        from purchases.dto.purchase_return_detail_dto import PurchaseReturnDetailDTO
        from purchases.use_cases.create_purchase_return import CreatePurchaseReturn
        dtype = DocumentType.objects.get(code="PURCHASE_RETURN")
        Sequence.objects.get_or_create(
            company=self.company, branch=self.branch, document_type=dtype,
            defaults=dict(name="Devoluciones C05", prefix="D5-", next_number=1),
        )
        return CreatePurchaseReturn.execute(PurchaseReturnCreateDTO(
            purchase_id=purchase.pk, issue_date=purchase.issue_date, notes="C05 return",
            details=[PurchaseReturnDetailDTO(purchase_detail_id=purchase.details.get().pk, quantity=Decimal("1"))],
        ))

    def test_purchase_return_uses_purchase_manifest_identity(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        document = self.make_return(purchase)
        from purchases.use_cases.confirm_purchase_return import ConfirmPurchaseReturn
        ConfirmPurchaseReturn.execute(document.pk)
        self.assertTrue(document.movement_manifest.exists())

    def test_purchase_return_rejects_missing_purchase_manifest(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        document = self.make_return(purchase)
        model.objects.get(purchase=purchase).delete()
        from purchases.use_cases.confirm_purchase_return import ConfirmPurchaseReturn
        with self.assertRaises(Exception):
            ConfirmPurchaseReturn.execute(document.pk)

    def test_purchase_return_uses_historical_warehouse_after_main_changes(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        Warehouse.objects.filter(pk=self.warehouse_a.pk).update(is_main=False)
        Warehouse.objects.filter(pk=self.warehouse_b.pk).update(is_main=True)
        self.assertEqual(self.original_movements(purchase).get().warehouse_id, self.warehouse_a.pk)

    def test_exact_set_rejects_same_count_different_id_substitution(self):
        model = self.model(self)
        if model is None:
            return
        first = self.confirm(self.make_purchase())
        second = self.confirm(self.make_purchase())
        first_movement = self.original_movements(first).get()
        second_movement = self.original_movements(second).get()
        StockMovement.objects.filter(pk=first_movement.pk).update(object_id=second.pk)
        StockMovement.objects.filter(pk=second_movement.pk).update(object_id=first.pk)
        with self.assertRaises(Exception):
            PurchaseCancellationService.cancel(first.pk)

    def test_purchase_return_rejects_extra_purchase_movement(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        document = self.make_return(purchase)
        from inventory.services.movement.create_stock_movement import CreateStockMovement
        CreateStockMovement().execute(company=self.company, branch=self.branch, warehouse=self.warehouse_a,
                                      product=self.product, quantity=Decimal("1"), unit_cost=Decimal("10"),
                                      movement_type=MovementType.PURCHASE, document=purchase)
        from purchases.use_cases.confirm_purchase_return import ConfirmPurchaseReturn
        with self.assertRaises(Exception):
            ConfirmPurchaseReturn.execute(document.pk)

    def test_purchase_return_rejects_same_count_different_id_history(self):
        model = self.model(self)
        if model is None:
            return
        first = self.confirm(self.make_purchase())
        second = self.confirm(self.make_purchase())
        document = self.make_return(first)
        first_movement = self.original_movements(first).get()
        second_movement = self.original_movements(second).get()
        StockMovement.objects.filter(pk=first_movement.pk).update(object_id=second.pk)
        StockMovement.objects.filter(pk=second_movement.pk).update(object_id=first.pk)
        from purchases.use_cases.confirm_purchase_return import ConfirmPurchaseReturn
        with self.assertRaises(Exception):
            ConfirmPurchaseReturn.execute(document.pk)
