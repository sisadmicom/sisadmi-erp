"""Contrato C-01: delta homogéneo, cantidades positivas, lifecycle e historia.

API prevista: CreateInventoryAdjustment.create_in/create_out(dto),
ConfirmInventoryAdjustment.execute(adjustment_id, user=None),
CancelInventoryAdjustment.execute(adjustment_id, user=None).
El DTO no recibe tipo documental; la operación pública lo determina.
"""
from dataclasses import fields
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase

from core.constants.document_type_codes import DocumentTypeCodes
from core.models import Branch, DocumentType, Sequence
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from inventory.services.stock import DecreaseStock, IncreaseStock
from inventory.tests.adjustment_test_support import AdjustmentFixture, QUANTITY, REJECTIONS, TYPE_CODES
from catalog.models import Product


class AdjustmentCatalogTests(TestCase):
    def test_canonical_codes_exist(self):
        for direction, code in TYPE_CODES.items():
            with self.subTest(direction=direction):
                self.assertEqual(getattr(DocumentTypeCodes, code, None), code)

    def test_migrated_catalog_has_both_operational_types(self):
        for direction, code in TYPE_CODES.items():
            with self.subTest(direction=direction):
                self.assertEqual(list(DocumentType.objects.filter(code=code).values(
                    "category", "line_behavior", "requires_detail", "affects_inventory",
                    "inventory_behavior", "can_issue_electronic", "is_active",
                )), [dict(
                    category="INVENTORY", line_behavior="QUANTITY", requires_detail=True,
                    affects_inventory=True, inventory_behavior=direction,
                    can_issue_electronic=False, is_active=True,
                )])


class AdjustmentCreationTests(AdjustmentFixture, TestCase):
    def test_in_and_out_create_unnumbered_drafts_without_effects(self):
        self.assertNotIn("document_type", {field.name for field in fields(self.CreateDTO)})
        self.assertNotIn("document_type_id", {field.name for field in fields(self.CreateDTO)})
        self.assertNotIn("document_type_code", {field.name for field in fields(self.CreateDTO)})
        for direction in TYPE_CODES:
            with self.subTest(direction=direction):
                adjustment = self.create(direction, details=[
                    self.line(self.product), self.line(self.second_product, "1.123456"),
                ])
                adjustment.refresh_from_db()
                self.assertEqual(adjustment.status, "DRAFT")
                self.assertEqual(adjustment.number, "")
                self.assertEqual(adjustment.warehouse, self.warehouse)
                self.assertEqual(adjustment.company, self.company)
                self.assertEqual(adjustment.branch, self.branch)
                self.assertEqual(adjustment.document_type.code, TYPE_CODES[direction])
                self.assertEqual(adjustment.notes, self.dto().notes)
                self.assertEqual(list(adjustment.details.order_by("line").values_list(
                    "line", "product_id", "quantity",
                )), [(1, self.product.pk, QUANTITY), (2, self.second_product.pk, Decimal("1.123456"))])
        self.assertFalse(Stock.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.assertEqual(list(Sequence.objects.order_by("pk").values_list("next_number", flat=True)), [1, 1])

    def test_draft_creation_preserves_existing_stock_and_sequence(self):
        stock = self.stock(reserved="2")
        before = list(Stock.objects.values())
        for direction in TYPE_CODES:
            with self.subTest(direction=direction):
                self.create(direction)
                self.assertEqual(list(Stock.objects.values()), before)
                self.assertFalse(StockMovement.objects.exists())
                self.sequences[direction].refresh_from_db()
                self.assertEqual(self.sequences[direction].next_number, 1)
        stock.refresh_from_db()
        self.assertEqual(stock.reserved_quantity, Decimal("2"))

    def test_invalid_structure_notes_and_quantities_leave_no_residue(self):
        cases = [("empty", dict(details=[]))]
        cases += [(f"notes-{value!r}", dict(notes=value)) for value in ("", "  \n\t", None)]
        cases += [(f"quantity-{value}", dict(details=[self.line(self.product, value)])) for value in (
            "0", "-0.004000", "NaN", "sNaN", "Infinity", "-Infinity",
            "0.0000001", "1.1234567", "1000000000000",
        )]
        cases.append(("duplicate-product", dict(details=[self.line(self.product), self.line(self.product)])))
        for direction in TYPE_CODES:
            for label, overrides in cases:
                with self.subTest(direction=direction, case=label):
                    self.assert_creation_rejected(direction, **overrides)

    def test_foreign_context_is_rejected_before_document_persistence(self):
        foreign_company = self.make_company("B")
        foreign_branch = Branch.objects.create(company=foreign_company, code="B", name="Ajena")
        local_branch = Branch.objects.create(company=self.company, code="A2", name="Otra")
        foreign_warehouse = Warehouse.objects.create(
            company=foreign_company, branch=foreign_branch, code="B", name="Ajena",
        )
        local_warehouse = Warehouse.objects.create(
            company=self.company, branch=local_branch, code="A2", name="Otra",
        )
        foreign_product = Product.objects.create(company=foreign_company, code="B", name="Ajeno")
        cases = dict(
            foreign_product=dict(details=[self.line(self.product), self.line(foreign_product)]),
            foreign_warehouse=dict(warehouse_id=foreign_warehouse.pk),
            other_branch_warehouse=dict(warehouse_id=local_warehouse.pk),
            foreign_branch=dict(branch_id=foreign_branch.pk),
        )
        for direction in TYPE_CODES:
            for label, overrides in cases.items():
                with self.subTest(direction=direction, case=label):
                    self.assert_creation_rejected(direction, **overrides)

    def test_missing_inactive_or_incompatible_type_is_rejected(self):
        for direction in TYPE_CODES:
            cases = [None, dict(is_active=False), dict(category="SALES"),
                     dict(line_behavior="COMMERCIAL"), dict(requires_detail=False),
                     dict(affects_inventory=False, inventory_behavior="NONE"),
                     dict(inventory_behavior="OUT" if direction == "IN" else "IN"),
                     dict(can_issue_electronic=True)]
            for changes in cases:
                with self.subTest(direction=direction, changes=changes), transaction.atomic():
                    if changes is None:
                        Sequence.objects.filter(document_type=self.types[direction]).delete()
                        DocumentType.objects.filter(code=TYPE_CODES[direction]).delete()
                    else:
                        DocumentType.objects.filter(code=TYPE_CODES[direction]).update(**changes)
                    # Ausencia de catálogo puede conservar el DoesNotExist del lookup.
                    with self.assertRaises(REJECTIONS + (DocumentType.DoesNotExist,)):
                        self.create(direction)
                    self.assertFalse(self.Adjustment.objects.exists())
                    self.assertFalse(self.Detail.objects.exists())
                    self.assertFalse(Stock.objects.exists())
                    self.assertFalse(StockMovement.objects.exists())
                    transaction.set_rollback(True)

    def test_detail_uniqueness_is_enforced_by_database(self):
        adjustment = self.create()
        for line, product in ((1, self.second_product), (2, self.product)):
            with self.subTest(line=line, product=product.pk):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.Detail.objects.create(
                        adjustment=adjustment, line=line, product=product, quantity=QUANTITY,
                    )
                self.assertEqual(adjustment.details.count(), 1)


class AdjustmentConfirmationTests(AdjustmentFixture, TestCase):
    def test_in_and_out_preserve_six_decimals_and_create_one_linked_movement(self):
        for direction, expected in (("IN", "10.004000"), ("OUT", "9.996000")):
            with self.subTest(direction=direction), transaction.atomic():
                stock = self.stock()
                adjustment = self.create(direction)
                self.confirm(adjustment)
                adjustment.refresh_from_db()
                stock.refresh_from_db()
                self.assertEqual(stock.quantity, Decimal(expected))
                self.assertEqual(adjustment.details.get().quantity, QUANTITY)
                self.assertEqual(adjustment.status, "CONFIRMED")
                self.assertTrue(adjustment.number)
                self.assertIsNotNone(adjustment.confirmed_at)
                movement = self.movements(adjustment).get()  # Exactamente uno.
                self.assertEqual(movement.movement_type, getattr(MovementType, f"ADJUSTMENT_{direction}"))
                self.assertEqual(movement.quantity, QUANTITY)
                self.assertEqual(movement.document, adjustment)
                self.assertEqual(movement.product, self.product)
                self.assertEqual(movement.warehouse, self.warehouse)
                self.assertIsNone(movement.reverses_id)
                self.sequences[direction].refresh_from_db()
                self.assertEqual(self.sequences[direction].next_number, 2)
                transaction.set_rollback(True)

    def test_second_confirmation_cannot_repeat_effect_or_number(self):
        adjustment = self.create()
        self.confirm(adjustment)
        self.assert_operation_rejected(adjustment, self.confirm)

    def test_out_rejects_absent_insufficient_or_reserved_stock(self):
        for quantity, reserved in ((None, "0"), ("0.003000", "0"), ("10", "9.997000")):
            with self.subTest(quantity=quantity, reserved=reserved), transaction.atomic():
                if quantity is not None:
                    self.stock(quantity=quantity, reserved=reserved)
                adjustment = self.create("OUT")
                self.assert_operation_rejected(adjustment, self.confirm)
                transaction.set_rollback(True)

    def test_second_line_effect_failure_rolls_back_everything(self):
        for direction, service in (("IN", IncreaseStock), ("OUT", DecreaseStock)):
            with self.subTest(direction=direction), transaction.atomic():
                self.stock()
                self.stock(self.second_product)
                adjustment = self.create(direction, details=[self.line(self.product), self.line(self.second_product)])
                before = self.snapshot(adjustment)
                real_execute = service.execute
                observed = []

                def effect_then_fail(instance, **kwargs):
                    result = real_execute(instance, **kwargs)
                    observed.append(self.movements(adjustment).count())
                    if len(observed) == 2:
                        raise RuntimeError("Fallo después del segundo efecto real")
                    return result

                with patch.object(service, "execute", new=effect_then_fail):
                    with self.assertRaisesMessage(RuntimeError, "segundo efecto real"):
                        self.confirm(adjustment)
                self.assertEqual(observed, [1, 2])
                self.assertEqual(self.snapshot(adjustment), before)
                transaction.set_rollback(True)

    def test_confirmation_revalidates_manipulated_draft(self):
        company = self.make_company("B")
        branch = Branch.objects.create(company=company, code="B", name="Ajena")
        warehouse = Warehouse.objects.create(company=company, branch=branch, code="B", name="Ajena")
        product = Product.objects.create(company=company, code="B", name="Ajeno")
        mutations = (
            ("header", dict(warehouse_id=warehouse.pk)),
            ("header", dict(branch_id=branch.pk)),
            ("header", dict(notes="")),
            ("header", dict(document_type_id=DocumentType.objects.get(code="INVENTORY_TRANSFER").pk)),
            ("detail", dict(product_id=product.pk)),
            ("detail", dict(quantity=Decimal("0"))),
            ("detail", dict(quantity=Decimal("-1"))),
            ("catalog", dict(is_active=False)),
        )
        for target, values in mutations:
            with self.subTest(target=target, values=values), transaction.atomic():
                adjustment = self.create()
                if target == "header":
                    self.Adjustment.objects.filter(pk=adjustment.pk).update(**values)
                elif target == "detail":
                    adjustment.details.update(**values)
                else:
                    DocumentType.objects.filter(pk=self.types["IN"].pk).update(**values)
                self.assert_operation_rejected(adjustment, self.confirm)
                transaction.set_rollback(True)


class AdjustmentCancellationTests(AdjustmentFixture, TestCase):
    def test_in_and_out_cancel_exact_historical_effect_with_linked_reversal(self):
        for direction, reversal_type in (("IN", MovementType.RETURN_OUT), ("OUT", MovementType.RETURN_IN)):
            with self.subTest(direction=direction), transaction.atomic():
                stock = self.stock()
                adjustment = self.create(direction)
                self.confirm(adjustment)
                adjustment.refresh_from_db()
                number = adjustment.number
                original = self.movements(adjustment).get()
                original_data = StockMovement.objects.values().get(pk=original.pk)
                self.cancel(adjustment)
                adjustment.refresh_from_db()
                stock.refresh_from_db()
                self.assertEqual(adjustment.status, "CANCELLED")
                self.assertIsNotNone(adjustment.cancelled_at)
                self.assertEqual(adjustment.number, number)
                self.assertEqual(stock.quantity, Decimal("10.000000"))
                self.assertEqual(StockMovement.objects.values().get(pk=original.pk), original_data)
                reversal = self.movements(adjustment).get(reverses=original)
                self.assertEqual(reversal.movement_type, reversal_type)
                self.assertEqual(reversal.quantity, QUANTITY)
                self.assertEqual(reversal.document, adjustment)
                self.assertEqual(reversal.product, original.product)
                self.assertEqual(reversal.warehouse, original.warehouse)
                self.assertEqual(self.movements(adjustment).count(), 2)
                self.sequences[direction].refresh_from_db()
                self.assertEqual(self.sequences[direction].next_number, 2)
                transaction.set_rollback(True)

    def test_cancel_ignores_mutated_or_deleted_details(self):
        for direction in TYPE_CODES:
            for delete in (False, True):
                with self.subTest(direction=direction, delete=delete), transaction.atomic():
                    stock = self.stock()
                    adjustment = self.create(direction)
                    self.confirm(adjustment)
                    original = self.movements(adjustment).get()
                    if delete:
                        adjustment.details.all().delete()
                    else:
                        adjustment.details.update(quantity=Decimal("7"), product=self.second_product)
                    self.cancel(adjustment)
                    stock.refresh_from_db()
                    self.assertEqual(stock.quantity, Decimal("10"))
                    reversal = self.movements(adjustment).get(reverses=original)
                    self.assertEqual(reversal.quantity, QUANTITY)
                    self.assertEqual(reversal.product, self.product)
                    self.assertEqual(self.movements(adjustment).count(), 2)
                    transaction.set_rollback(True)

    def test_draft_and_second_cancellation_are_rejected(self):
        adjustment = self.create()
        self.assert_operation_rejected(adjustment, self.cancel)
        self.confirm(adjustment)
        self.cancel(adjustment)
        self.assert_operation_rejected(adjustment, self.cancel)

    def test_missing_or_inconsistent_history_is_rejected(self):
        for mutation in ("missing", "mixed-directions"):
            with self.subTest(mutation=mutation), transaction.atomic():
                adjustment = self.create(details=[self.line(self.product), self.line(self.second_product)])
                self.confirm(adjustment)
                if mutation == "missing":
                    self.movements(adjustment).delete()
                else:
                    self.movements(adjustment).filter(product=self.second_product).update(
                        movement_type=MovementType.ADJUSTMENT_OUT,
                    )
                self.assert_operation_rejected(adjustment, self.cancel)
                transaction.set_rollback(True)

    def test_consumed_input_cannot_cancel_without_available_stock(self):
        adjustment = self.create()
        self.confirm(adjustment)
        DecreaseStock().execute(
            company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=self.product, quantity=QUANTITY, movement_type=MovementType.ADJUSTMENT_OUT,
        )
        self.assert_operation_rejected(adjustment, self.cancel)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, "CONFIRMED")

    def test_second_reversal_failure_leaves_no_partial_compensation(self):
        adjustment = self.create(details=[self.line(self.product), self.line(self.second_product)])
        self.confirm(adjustment)
        before = self.snapshot(adjustment)
        real_reverse = StockMovementReversalService.reverse
        observed = []

        def reverse_then_fail(**kwargs):
            result = real_reverse(**kwargs)
            observed.append(self.movements(adjustment).filter(reverses__isnull=False).count())
            if len(observed) == 2:
                raise RuntimeError("Fallo después de segunda reversión real")
            return result

        with patch.object(StockMovementReversalService, "reverse", side_effect=reverse_then_fail):
            with self.assertRaisesMessage(RuntimeError, "segunda reversión real"):
                self.cancel(adjustment)
        self.assertEqual(observed, [1, 2])
        self.assertEqual(self.snapshot(adjustment), before)
