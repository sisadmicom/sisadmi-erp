"""Contrato C-03 activo: RED por feature ausente, sin implementar producción."""
from dataclasses import fields, is_dataclass
from decimal import Decimal, ROUND_HALF_UP
from unittest.mock import patch

from django.apps import apps
from django.db import IntegrityError, connection, models, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext

from catalog.models import Product, Tax, TaxConfiguration
from catalog.services.tax_resolver import TaxResolver
from core.constants.document_status import DocumentStatus
from core.constants.document_type_codes import DocumentTypeCodes
from core.models import (BaseDocument, BaseDocumentLine, CommercialAmountsMixin,
                         DocumentType, QuantityLineMixin, Sequence)
from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from inventory.services.stock import DecreaseStock
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.models import Purchase, PurchaseDetail, PurchaseMovement
from purchases.tests.purchase_return_test_support import (
    MONEY_FIELDS, REJECTIONS, PurchaseReturnFixture, movements, persisted_state, return_api, return_models,
)
from purchases.use_cases.cancel_purchase import CancelPurchase


@tag("c03_purchase_return")
class PurchaseReturnCatalogTests(TestCase):
    def test_document_type_code(self):
        self.assertEqual(DocumentTypeCodes.PURCHASE_RETURN, "PURCHASE_RETURN")

    def test_migrated_catalog_capabilities(self):
        # El literal permite diagnosticar la fila ausente independientemente del código.
        self.assertEqual(list(DocumentType.objects.filter(code="PURCHASE_RETURN").values(
            "category", "line_behavior", "requires_detail", "affects_inventory",
            "inventory_behavior", "can_issue_electronic", "is_active")), [{
                "category": "PURCHASES", "line_behavior": "COMMERCIAL",
                "requires_detail": True, "affects_inventory": True,
                "inventory_behavior": "OUT", "can_issue_electronic": False, "is_active": True,
            }])


class PurchaseReturnAPIAndModelsTests(PurchaseReturnFixture, TestCase):
    def test_dto_dataclasses_expose_only_origin_date_notes_and_quantities(self):
        DTO, Line, *_ = return_api()
        self.assertTrue(is_dataclass(DTO))
        self.assertTrue(is_dataclass(Line))
        self.assertEqual({field.name for field in fields(DTO)},
                         {"purchase_id", "issue_date", "notes", "details"})
        self.assertEqual({field.name for field in fields(Line)}, {"purchase_detail_id", "quantity"})
        forbidden = ("company_id", "branch_id", "supplier_id", "warehouse_id", "product_id",
                     "unit_price", "discount", "tax", "tax_amount", "document_type",
                     "direction", "unit_cost")
        for field in forbidden:
            with self.subTest(field=field):
                with self.assertRaises(TypeError):
                    DTO(purchase_id=self.purchase.pk, issue_date=self.purchase.issue_date,
                        notes="", details=[], **{field: 1})
                with self.assertRaises(TypeError):
                    Line(purchase_detail_id=self.purchase.details.get().pk,
                         quantity=Decimal("1"), **{field: 1})

    def test_document_and_line_inheritance_and_protected_foreign_keys(self):
        Return, Detail = return_models()
        self.assertTrue(issubclass(Return, BaseDocument))
        for base in (BaseDocumentLine, QuantityLineMixin, CommercialAmountsMixin):
            self.assertTrue(issubclass(Detail, base))
        for model, name, target in (
            (Return, "purchase", Purchase), (Return, "warehouse", Warehouse),
            (Detail, "purchase_detail", PurchaseDetail), (Detail, "product", Product),
        ):
            field = model._meta.get_field(name)
            self.assertIs(field.remote_field.model, target)
            self.assertIs(field.remote_field.on_delete, models.PROTECT)
        self.assertIs(Detail._meta.get_field("purchase_return").remote_field.model, Return)
        for name in ("subtotal", "tax", "total"):
            self.assertIsInstance(Return._meta.get_field(name), models.DecimalField)
        quantity = Detail._meta.get_field("quantity")
        self.assertEqual((quantity.max_digits, quantity.decimal_places), (18, 6))
        self.assertNotIn("returned_quantity", {f.name for f in PurchaseDetail._meta.fields})

    def test_origin_purchase_and_detail_cannot_be_deleted(self):
        document = self.make_return()
        for origin in (self.purchase.details.get(), self.purchase):
            with self.subTest(origin=origin._meta.label):
                with self.assertRaises(ProtectedError), transaction.atomic():
                    origin.delete()
        self.assertTrue(type(document).objects.filter(pk=document.pk).exists())

    def test_no_purchase_return_detail_tax_model_or_table(self):
        self.make_return()
        self.assertNotIn("purchasereturndetailtax", apps.all_models["purchases"])
        self.assertFalse(any("purchasereturndetailtax" in name.replace("_", "").lower()
                             for name in connection.introspection.table_names()))

    def test_unique_return_line_is_enforced_by_database(self):
        _, Line, *_ = return_api()
        purchase = self.two_line_purchase()
        first, second = list(purchase.details.order_by("line"))
        document = self.make_return(purchase=purchase, details=[Line(first.pk, Decimal("1"))])
        existing = document.details.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            type(existing).objects.create(
                purchase_return=document, purchase_detail=second, line=existing.line,
                product=second.product, quantity=Decimal("1"))
        self.assertEqual(document.details.count(), 1)

    def test_unique_return_purchase_detail_is_enforced_by_database(self):
        document = self.make_return()
        existing = document.details.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            type(existing).objects.create(
                purchase_return=document, purchase_detail=existing.purchase_detail,
                line=existing.line + 1, product=existing.product, quantity=Decimal("1"))
        self.assertEqual(document.details.count(), 1)

    def test_no_database_quantity_positive_check(self):
        document = self.make_return()
        detail = document.details.get()
        # Escritura ORM deliberadamente fuera del dominio: demuestra la frontera DB.
        for value in (Decimal("0"), Decimal("-1")):
            type(detail).objects.filter(pk=detail.pk).update(quantity=value)
            detail.refresh_from_db()
            self.assertEqual(detail.quantity, value)
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, detail._meta.db_table)
        self.assertFalse(any(c["check"] and "quantity" in c["columns"]
                             for c in constraints.values()))


class PurchaseReturnCreationTests(PurchaseReturnFixture, TestCase):
    def test_total_partial_and_independent_drafts_have_no_operational_effect(self):
        return_api()
        sequence = self.return_sequence()
        stock_before = list(Stock.objects.order_by("pk").values())
        movements_before = list(StockMovement.objects.order_by("pk").values())
        sequences_before = list(Sequence.objects.order_by("pk").values())
        documents = [self.make_return(qty) for qty in ("10", "3", "3")]
        self.assertEqual(len({doc.pk for doc in documents}), 3)
        for document, quantity in zip(documents, ("10", "3", "3")):
            document.refresh_from_db()
            self.assertEqual(document.status, DocumentStatus.DRAFT)
            self.assertEqual(document.number, "")
            self.assertIsNone(document.confirmed_at)
            self.assertEqual(document.notes, "")
            self.assertEqual(document.purchase_id, self.purchase.pk)
            self.assertEqual(document.company_id, self.company.pk)
            self.assertEqual(document.branch_id, self.branch.pk)
            self.assertEqual(document.purchase.supplier_id, self.supplier.pk)
            self.assertEqual(document.warehouse_id, self.warehouse.pk)
            self.assertEqual(document.document_type.code, DocumentTypeCodes.PURCHASE_RETURN)
            detail = document.details.get()
            self.assertEqual(detail.purchase_detail_id, self.purchase.details.get().pk)
            self.assertEqual(detail.product_id, self.product.pk)
            self.assertEqual(detail.quantity, Decimal(quantity))
            self.assertFalse(movements(document).exists())
        self.assertEqual(list(Stock.objects.order_by("pk").values()), stock_before)
        self.assertEqual(list(StockMovement.objects.order_by("pk").values()), movements_before)
        self.assertEqual(list(Sequence.objects.order_by("pk").values()), sequences_before)
        sequence.refresh_from_db()
        self.assertEqual(sequence.next_number, 1)

    def test_creation_does_not_require_or_create_a_return_sequence(self):
        _, _, Create, *_ = return_api()
        before = list(Sequence.objects.order_by("pk").values())
        document = Create.execute(self.dto())
        self.assertEqual(document.number, "")
        self.assertEqual(document.status, DocumentStatus.DRAFT)
        self.assertEqual(list(Sequence.objects.order_by("pk").values()), before)

    def test_invalid_quantity_is_rejected_without_rows_or_effects(self):
        DTO, Line, Create, *_ = return_api()
        self.return_sequence()
        invalid = [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"),
                   Decimal("-Infinity"), Decimal("1.0000001"), Decimal("1000000000000"),
                   1, 1.5, "1"]
        for quantity in invalid:
            with self.subTest(quantity=repr(quantity)):
                def create():
                    return Create.execute(DTO(
                        purchase_id=self.purchase.pk, issue_date=self.purchase.issue_date, notes="",
                        details=[Line(purchase_detail_id=self.purchase.details.get().pk, quantity=quantity)]))
                self.assert_rejected_unchanged(create)

    def test_six_decimal_quantity_survives_database_and_inventory(self):
        document = self.make_return("0.000001")
        before = self.stock().quantity
        self.confirm_return(document)
        self.assertEqual(document.details.get().quantity, Decimal("0.000001"))
        self.assertEqual(movements(document, MovementType.RETURN_OUT).get().quantity, Decimal("0.000001"))
        self.assertEqual(self.stock().quantity, before - Decimal("0.000001"))

    def test_empty_or_duplicate_lines_are_rejected_atomically(self):
        _, Line, Create, *_ = return_api()
        self.return_sequence()
        source = self.purchase.details.get()
        for details in ([], [Line(source.pk, Decimal("1")), Line(source.pk, Decimal("2"))]):
            with self.subTest(count=len(details)):
                self.assert_rejected_unchanged(lambda: Create.execute(self.dto(details=details)))

    def test_missing_purchase_is_a_domain_rejection(self):
        _, _, Create, *_ = return_api()
        dto = self.dto()
        discarded = self.make_purchase(confirm=False)
        dto.purchase_id = discarded.pk
        discarded.delete()
        self.assert_rejected_unchanged(lambda: Create.execute(dto))

    def test_purchase_must_be_confirmed_at_creation(self):
        _, _, Create, *_ = return_api()
        draft = self.make_purchase(confirm=False)
        cancelled = self.make_purchase()
        CancelPurchase.execute(purchase_id=cancelled.pk, user=None)
        for purchase in (draft, cancelled):
            with self.subTest(purchase=purchase.pk):
                self.assert_rejected_unchanged(lambda: Create.execute(self.dto(purchase=purchase)))

    def test_detail_from_another_purchase_is_rejected(self):
        _, Line, Create, *_ = return_api()
        other = self.make_purchase()
        self.assert_rejected_unchanged(lambda: Create.execute(self.dto(
            details=[Line(other.details.get().pk, Decimal("1"))])))


class PurchaseReturnHistoricalOriginTests(PurchaseReturnFixture, TestCase):
    def test_warehouse_is_derived_from_purchase_history_despite_new_main(self):
        return_api()
        Warehouse.objects.filter(pk=self.warehouse.pk).update(is_main=False)
        current = Warehouse.objects.create(company=self.company, branch=self.branch,
                                           code="B", name="Principal nueva B", is_main=True)
        document = self.make_return()
        self.assertEqual(document.warehouse_id, self.warehouse.pk)
        self.confirm_return(document)
        self.assertEqual(movements(document, MovementType.RETURN_OUT).get().warehouse_id, self.warehouse.pk)
        self.assertEqual(self.stock().quantity, Decimal("7"))
        self.assertFalse(Stock.objects.filter(warehouse=current).exists())

    def test_purchase_without_purchase_movements_is_rejected(self):
        _, _, Create, *_ = return_api()
        # La historia física queda protegida por PROTECT; corrompemos solo
        # la identidad del manifest eliminando su fila PurchaseMovement.
        PurchaseMovement.objects.filter(purchase=self.purchase).delete()
        self.assert_rejected_unchanged(lambda: Create.execute(self.dto()))

    def test_multiple_historical_warehouses_are_rejected_without_first_heuristic(self):
        _, _, Create, *_ = return_api()
        purchase = self.two_line_purchase()
        other = Warehouse.objects.create(company=self.company, branch=self.branch,
                                         code="B", name="B")
        # Corrupción controlada: compra confirmó sus dos líneas en A.
        movements(purchase, MovementType.PURCHASE).filter(product=self.product2).update(warehouse=other)
        _, Line, *_ = return_api()
        details = [Line(purchase.details.get(product=self.product).pk, Decimal("1"))]
        self.assert_rejected_unchanged(lambda: Create.execute(self.dto(purchase=purchase, details=details)))

    def test_repeated_product_with_distinct_historical_costs_is_ambiguous(self):
        _, Line, Create, Confirm, _ = return_api()
        purchase = self.make_purchase(lines=[
            PurchaseDetailDTO(self.product.pk, Decimal("5"), Decimal("10")),
            PurchaseDetailDTO(self.product.pk, Decimal("5"), Decimal("20")),
        ])
        self.assertEqual(set(movements(purchase, MovementType.PURCHASE).values_list("unit_cost", flat=True)),
                         {Decimal("10"), Decimal("20")})
        self.return_sequence()
        dto = self.dto(purchase=purchase, details=[
            Line(purchase.details.order_by("line")[0].pk, Decimal("1"))])
        # Rechazar al crear o confirmar es válido; no puede llegar a efecto físico.
        before_stock = list(Stock.objects.order_by("pk").values())
        before_movements = list(StockMovement.objects.order_by("pk").values())
        before_sequences = list(Sequence.objects.order_by("pk").values())
        with self.assertRaises(REJECTIONS):
            document = Create.execute(dto)
            draft_state = persisted_state()
            try:
                Confirm.execute(purchase_return_id=document.pk, user=None)
            except REJECTIONS:
                self.assertEqual(persisted_state(), draft_state)
                raise
        self.assertEqual(list(Stock.objects.order_by("pk").values()), before_stock)
        self.assertEqual(list(StockMovement.objects.order_by("pk").values()), before_movements)
        self.assertEqual(list(Sequence.objects.order_by("pk").values()), before_sequences)

    def test_cost_comes_from_unambiguous_history_not_current_product_cost(self):
        document = self.make_return()
        original = movements(self.purchase, MovementType.PURCHASE).get()
        self.assertEqual(original.unit_cost, Decimal("10"))
        Product.objects.filter(pk=self.product.pk).update(cost_price=Decimal("99.99"))
        self.confirm_return(document)
        self.assertEqual(movements(document, MovementType.RETURN_OUT).get().unit_cost, original.unit_cost)

    def test_corrupt_purchase_company_branch_is_rejected(self):
        _, _, Create, *_ = return_api()
        company, _, _, _ = self.new_context()
        Purchase.objects.filter(pk=self.purchase.pk).update(company=company)
        self.assert_rejected_unchanged(lambda: Create.execute(self.dto()))

    def test_corrupt_original_product_snapshot_is_rejected(self):
        _, _, Create, *_ = return_api()
        # Producto válido de la misma empresa pero distinto al recibido históricamente.
        self.purchase.details.update(product=self.product2)
        self.assert_rejected_unchanged(lambda: Create.execute(self.dto()))

    def test_foreign_company_product_is_rejected(self):
        _, _, Create, *_ = return_api()
        _, _, _, foreign = self.new_context()
        self.purchase.details.update(product=foreign)
        self.assert_rejected_unchanged(lambda: Create.execute(self.dto()))

    def test_each_corrupt_purchase_movement_context_is_rejected(self):
        _, _, Create, *_ = return_api()
        company, branch, warehouse, product = self.new_context()
        original = movements(self.purchase, MovementType.PURCHASE).get()
        for field, value in (("company_id", company.pk), ("branch_id", branch.pk),
                             ("warehouse_id", warehouse.pk), ("product_id", product.pk)):
            with self.subTest(field=field):
                old = getattr(original, field)
                StockMovement.objects.filter(pk=original.pk).update(**{field: value})
                self.assert_rejected_unchanged(lambda: Create.execute(self.dto()))
                StockMovement.objects.filter(pk=original.pk).update(**{field: old})

    def test_confirmation_revalidates_return_product_and_context(self):
        document = self.make_return()
        company, branch, warehouse, _ = self.new_context()
        detail = document.details.get()
        for model, pk, field, value in (
            (type(detail), detail.pk, "product_id", self.product2.pk),
            (type(document), document.pk, "company_id", company.pk),
            (type(document), document.pk, "branch_id", branch.pk),
            (type(document), document.pk, "warehouse_id", warehouse.pk),
        ):
            with self.subTest(field=field):
                old = model.objects.values_list(field, flat=True).get(pk=pk)
                model.objects.filter(pk=pk).update(**{field: value})
                self.assert_rejected_unchanged(lambda: self.confirm_return(document))
                model.objects.filter(pk=pk).update(**{field: old})

    def test_confirmation_revalidates_source_history_after_draft(self):
        document = self.make_return()
        # El movimiento original no puede eliminarse mientras está
        # manifestado. La corrupción entre draft y confirmación es la
        # desaparición del manifest, que debe volver a validarse.
        PurchaseMovement.objects.filter(purchase=self.purchase).delete()
        self.assert_rejected_unchanged(lambda: self.confirm_return(document))


class PurchaseReturnCommercialTests(PurchaseReturnFixture, TestCase):
    def test_confirmed_quantities_only_limit_returnable_and_cancel_releases(self):
        unused = self.make_return("10")
        a = self.make_return("3")
        b = self.make_return("7")
        c = self.make_return("1")
        self.confirm_return(a)
        self.assertEqual(self.stock().quantity, Decimal("7"))
        self.confirm_return(b)
        self.assertEqual(self.stock().quantity, Decimal("0"))
        self.assert_rejected_unchanged(lambda: self.confirm_return(c))
        unused.refresh_from_db()
        self.assertEqual(unused.status, DocumentStatus.DRAFT)
        self.cancel_return(a)
        released = self.make_return("3")
        self.confirm_return(released)
        _, Detail = return_models()
        quantities = Detail.objects.filter(purchase_detail=self.purchase.details.get(),
                                          purchase_return__status=DocumentStatus.CONFIRMED)
        self.assertEqual(sum(quantities.values_list("quantity", flat=True)), Decimal("10"))
        self.assertEqual(self.stock().quantity, Decimal("0"))
        self.assert_rejected_unchanged(lambda: self.confirm_return(c))

    def test_snapshot_and_nonzero_aggregate_tax_ignore_current_catalog(self):
        purchase = self.monetary_purchase()
        source = purchase.details.get()
        self.assertEqual(source.tax_amount, Decimal("0.01"))
        document = self.make_return("3", purchase=purchase)
        Product.objects.filter(pk=self.product.pk).update(sale_price=Decimal("999"), cost_price=Decimal("88"))
        tax = Tax.objects.create(company=self.company, name="Impuesto actual", code="C03-TAX",
                                 tax_type="IVA", rate=Decimal("25"))
        self.product.taxes.add(tax)
        config = TaxConfiguration.objects.create(company=self.company)
        config.taxes.add(tax)
        with patch.object(TaxResolver, "resolve", wraps=TaxResolver.resolve) as resolver:
            with CaptureQueriesContext(connection) as queries:
                self.confirm_return(document)
            resolver.assert_not_called()
        config_table = TaxConfiguration._meta.db_table.lower()
        self.assertFalse(any(config_table in row["sql"].lower() for row in queries))
        actual = document.details.get()
        self.assertEqual(actual.product_id, source.product_id)
        self.assertEqual(actual.unit_price, source.unit_price)
        for field in MONEY_FIELDS:
            self.assertEqual(getattr(actual, field), getattr(source, field), field)
        self.assertEqual((document.subtotal, document.tax, document.total),
                         (source.subtotal, source.tax_amount, source.total))
        self.assertNotIn("purchasereturndetailtax", apps.all_models["purchases"])

    def test_draft_creation_does_not_resolve_or_query_current_taxes(self):
        purchase = self.monetary_purchase()
        self.return_sequence()
        with patch.object(TaxResolver, "resolve", wraps=TaxResolver.resolve) as resolver:
            with CaptureQueriesContext(connection) as queries:
                document = self.make_return("3", purchase=purchase)
            resolver.assert_not_called()
        self.assertFalse(any(TaxConfiguration._meta.db_table.lower() in row["sql"].lower()
                             for row in queries))
        self.confirm_return(document)
        self.assertEqual(document.details.get().tax_amount, Decimal("0.01"))

    def test_three_partials_reconcile_actual_persisted_cent_residue(self):
        purchase = self.monetary_purchase()
        source = purchase.details.get()
        # Valores manuales del caso: no se reutiliza ningún calculador productivo.
        self.assertEqual(tuple(getattr(source, f) for f in MONEY_FIELDS),
                         (Decimal("0.01"), Decimal("1.01"), Decimal("0.01"), Decimal("1.02")))
        naive = (source.subtotal / 3).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.assertEqual(naive, Decimal("0.34"))
        self.assertEqual(naive * 3 - source.subtotal, Decimal("0.01"))
        documents = []
        for _ in range(3):
            document = self.make_return("1", purchase=purchase)
            self.confirm_return(document)
            documents.append(document)
        self.assert_reconciled(purchase)
        persisted = [document.details.get() for document in documents]
        self.assertEqual([line.subtotal for line in persisted],
                         [Decimal("0.34"), Decimal("0.34"), Decimal("0.33")])
        self.assertEqual([line.discount for line in persisted],
                         [Decimal("0.00"), Decimal("0.00"), Decimal("0.01")])
        self.assertEqual([line.tax_amount for line in persisted],
                         [Decimal("0.00"), Decimal("0.00"), Decimal("0.01")])
        for document, line in zip(documents, persisted):
            self.assertEqual(line.total, Decimal("0.34"))
            self.assertEqual(line.unit_price, source.unit_price)
            self.assertEqual((document.subtotal, document.tax, document.total),
                             (line.subtotal, line.tax_amount, line.total))

    def test_intermediate_cancellation_reconciles_without_rewriting_confirmed_return(self):
        purchase = self.monetary_purchase()
        excessive = self.make_return("2", purchase=purchase)
        a = self.confirm_return(self.make_return("1", purchase=purchase))
        b = self.confirm_return(self.make_return("2", purchase=purchase))
        self.assert_reconciled(purchase)
        b_before = list(type(b).objects.filter(pk=b.pk).values())
        b_lines_before = list(b.details.order_by("pk").values())
        self.cancel_return(a)
        # Solo una unidad quedó liberada; dos tienen que ser rechazadas.
        self.assert_rejected_unchanged(lambda: self.confirm_return(excessive))
        c = self.confirm_return(self.make_return("1", purchase=purchase))
        self.assert_reconciled(purchase)
        self.assertEqual(list(type(b).objects.filter(pk=b.pk).values()), b_before)
        self.assertEqual(list(b.details.order_by("pk").values()), b_lines_before)
        self.assertEqual(tuple(getattr(c.details.get(), f) for f in MONEY_FIELDS),
                         (Decimal("0.00"), Decimal("0.34"), Decimal("0.00"), Decimal("0.34")))
        self.assertEqual(a.status, DocumentStatus.CANCELLED)


class PurchaseReturnConfirmationTests(PurchaseReturnFixture, TestCase):
    def test_confirmation_numbers_once_and_creates_one_historical_out_per_line(self):
        document = self.make_return("3")
        sequence = self.return_sequence()
        first = sequence.next_number
        purchase_next = Sequence.objects.get(pk=self.sequence.pk).next_number
        self.assertEqual(document.number, "")
        self.confirm_return(document)
        self.assertEqual(document.status, DocumentStatus.CONFIRMED)
        self.assertIsNotNone(document.confirmed_at)
        self.assertEqual(document.number,
                         f"{sequence.prefix}{sequence.series}-{str(first).zfill(sequence.padding)}")
        sequence.refresh_from_db()
        self.assertEqual(sequence.next_number, first + 1)
        self.assertEqual(Sequence.objects.get(pk=self.sequence.pk).next_number, purchase_next)
        self.assertEqual(self.stock().quantity, Decimal("7"))
        movement = movements(document).get()
        self.assertEqual(movement.movement_type, MovementType.RETURN_OUT)
        self.assertEqual(movement.quantity, Decimal("3"))
        self.assertEqual(movement.unit_cost, Decimal("10"))
        self.assertEqual(movement.warehouse_id, self.warehouse.pk)
        self.assertEqual(movement.product_id, self.product.pk)
        self.assertEqual((movement.company_id, movement.branch_id), (self.company.pk, self.branch.pk))
        self.assertEqual(movement.document, document)
        self.assertIsNone(movement.reverses_id)
        self.assert_rejected_unchanged(lambda: self.confirm_return(document))

    def test_confirmation_revalidates_persisted_quantity(self):
        document = self.make_return()
        detail = document.details.get()
        for quantity in (Decimal("0"), Decimal("-1"), Decimal("11")):
            with self.subTest(quantity=quantity):
                type(detail).objects.filter(pk=detail.pk).update(quantity=quantity)
                self.assert_rejected_unchanged(lambda: self.confirm_return(document))

    def test_stock_consumed_by_other_process_is_not_commercial_returnable(self):
        document = self.make_return("8")
        DecreaseStock().execute(company=self.company, branch=self.branch, warehouse=self.warehouse,
                                product=self.product, quantity=Decimal("4"),
                                movement_type=MovementType.ADJUSTMENT_OUT)
        self.assertEqual(self.stock().available_quantity, Decimal("6"))
        self.assert_rejected_unchanged(lambda: self.confirm_return(document))
        document.refresh_from_db()
        self.assertEqual((document.status, document.number), (DocumentStatus.DRAFT, ""))
        self.assertFalse(movements(document).exists())

    def test_reserved_stock_reduces_available_quantity(self):
        document = self.make_return("8")
        # ReserveStock es un stub; se configura la reserva persistida que lee DecreaseStock.
        Stock.objects.filter(pk=self.stock().pk).update(reserved_quantity=Decimal("3"))
        self.assertEqual(self.stock().quantity, Decimal("10"))
        self.assertEqual(self.stock().available_quantity, Decimal("7"))
        self.assert_rejected_unchanged(lambda: self.confirm_return(document))
        self.assertEqual(self.stock().reserved_quantity, Decimal("3"))

    def test_second_line_insufficient_stock_rolls_back_first_line_and_snapshots(self):
        _, Line, *_ = return_api()
        purchase = self.two_line_purchase()
        details = list(purchase.details.order_by("line"))
        document = self.make_return(purchase=purchase, details=[Line(d.pk, Decimal("8")) for d in details])
        DecreaseStock().execute(company=self.company, branch=self.branch, warehouse=self.warehouse,
                                product=self.product2, quantity=Decimal("4"),
                                movement_type=MovementType.ADJUSTMENT_OUT)
        first_stock = self.stock().quantity
        self.assert_rejected_unchanged(lambda: self.confirm_return(document))
        self.assertEqual(self.stock().quantity, first_stock)
        document.refresh_from_db()
        self.assertEqual((document.status, document.number), (DocumentStatus.DRAFT, ""))
        self.assertFalse(movements(document).exists())


class PurchaseReturnCancellationTests(PurchaseReturnFixture, TestCase):
    def test_draft_cannot_be_cancelled(self):
        document = self.make_return()
        self.assert_rejected_unchanged(lambda: self.cancel_return(document))

    def test_cancellation_uses_history_after_detail_mutation_and_preserves_number(self):
        document = self.confirm_return(self.make_return())
        original = movements(document, MovementType.RETURN_OUT).get()
        number = document.number
        document.details.update(quantity=Decimal("9"), unit_price=Decimal("999"), product=self.product2)
        self.cancel_return(document)
        self.assertEqual(document.status, DocumentStatus.CANCELLED)
        self.assertEqual(document.number, number)
        self.assertEqual(self.stock().quantity, Decimal("10"))
        self.assert_reversal(document, original, MovementType.RETURN_IN)
        self.assertEqual(movements(document).count(), 2)
        self.assert_rejected_unchanged(lambda: self.cancel_return(document))
        self.assert_rejected_unchanged(lambda: self.confirm_return(document))

    def test_cancellation_uses_history_after_all_return_details_are_deleted(self):
        document = self.confirm_return(self.make_return())
        original = movements(document, MovementType.RETURN_OUT).get()
        document.details.all().delete()
        self.assertEqual(document.details.count(), 0)
        self.cancel_return(document)
        self.assertEqual(document.status, DocumentStatus.CANCELLED)
        self.assertEqual(self.stock().quantity, Decimal("10"))
        self.assert_reversal(document, original, MovementType.RETURN_IN)

    def test_reversal_service_completes_before_document_service_cancels(self):
        document = self.confirm_return(self.make_return())
        original = movements(document, MovementType.RETURN_OUT).get()
        reverse = StockMovementReversalService.reverse
        cancel = DocumentService.cancel
        order = []

        def reverse_real(**kwargs):
            document.refresh_from_db()
            self.assertEqual(document.status, DocumentStatus.CONFIRMED)
            result = reverse(**kwargs)
            order.append("reverse")
            return result

        def cancel_real(*args, **kwargs):
            self.assert_reversal(document, original, MovementType.RETURN_IN)
            self.assertEqual(self.stock().quantity, Decimal("10"))
            order.append("cancel")
            return cancel(*args, **kwargs)

        with patch.object(StockMovementReversalService, "reverse", side_effect=reverse_real):
            with patch.object(DocumentService, "cancel", side_effect=cancel_real):
                self.cancel_return(document)
        self.assertEqual(order, ["reverse", "cancel"])

    def test_missing_return_out_rejects_cancellation_atomically(self):
        document = self.confirm_return(self.make_return())
        # Corrupción de TEST: conserva la fila protegida, pero la excluye
        # del conjunto original RETURN_OUT consultable. No pasa por servicios.
        movements(document, MovementType.RETURN_OUT).update(movement_type=MovementType.ADJUSTMENT_OUT)
        self.assert_rejected_unchanged(lambda: self.cancel_return(document))

    def test_already_reversed_return_out_rejects_cancellation_atomically(self):
        document = self.confirm_return(self.make_return())
        original = movements(document, MovementType.RETURN_OUT).get()
        StockMovementReversalService.reverse(movement=original, reversal_type=MovementType.RETURN_IN)
        self.assert_rejected_unchanged(lambda: self.cancel_return(document))
        self.assertEqual(original.reversal_movements.count(), 1)

    def test_incomplete_multiline_history_cannot_cancel_document(self):
        _, Line, *_ = return_api()
        purchase = self.two_line_purchase()
        document = self.make_return(purchase=purchase, details=[
            Line(detail.pk, Decimal("3")) for detail in purchase.details.order_by("line")])
        self.confirm_return(document)
        self.assertEqual(movements(document, MovementType.RETURN_OUT).count(), 2)
        # Corrupción de TEST: expected={A,B}, actual={A}; B sigue existiendo
        # y manifestado. PROTECT no se desactiva ni se intenta borrar su fila.
        movements(document, MovementType.RETURN_OUT).filter(product=self.product2).update(
            movement_type=MovementType.ADJUSTMENT_OUT)
        self.assert_rejected_unchanged(lambda: self.cancel_return(document))
        self.assertFalse(movements(document, MovementType.RETURN_IN).exists())

    def test_second_corrupt_movement_rolls_back_all_reversals(self):
        _, Line, *_ = return_api()
        purchase = self.two_line_purchase()
        document = self.make_return(purchase=purchase, details=[
            Line(detail.pk, Decimal("3")) for detail in purchase.details.order_by("line")])
        self.confirm_return(document)
        _, foreign_branch, _, _ = self.new_context()
        movements(document, MovementType.RETURN_OUT).filter(product=self.product2).update(branch=foreign_branch)
        self.assert_rejected_unchanged(lambda: self.cancel_return(document))
        self.assertFalse(movements(document, MovementType.RETURN_IN).exists())


class PurchaseReturnPurchaseInteractionTests(PurchaseReturnFixture, TestCase):
    def test_existing_purchase_without_return_still_cancels_real_history(self):
        original = movements(self.purchase, MovementType.PURCHASE).get()
        CancelPurchase.execute(purchase_id=self.purchase.pk, user=None)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, DocumentStatus.CANCELLED)
        self.assertEqual(self.stock().quantity, Decimal("0"))
        self.assert_reversal(self.purchase, original, MovementType.RETURN_OUT)
        self.assertEqual(movements(self.purchase).count(), 2)

    def test_draft_return_does_not_block_purchase_cancel_but_cannot_later_confirm(self):
        document = self.make_return()
        original = movements(self.purchase, MovementType.PURCHASE).get()
        CancelPurchase.execute(purchase_id=self.purchase.pk, user=None)
        self.purchase.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(self.purchase.status, DocumentStatus.CANCELLED)
        self.assertEqual(document.status, DocumentStatus.DRAFT)
        self.assertEqual(self.stock().quantity, Decimal("0"))
        self.assert_reversal(self.purchase, original, MovementType.RETURN_OUT)
        self.assertFalse(movements(document).exists())
        self.assert_rejected_unchanged(lambda: self.confirm_return(document))

    def test_confirmed_return_blocks_purchase_cancel_before_any_effect(self):
        document = self.confirm_return(self.make_return())
        self.assert_rejected_unchanged(lambda: CancelPurchase.execute(purchase_id=self.purchase.pk, user=None))
        self.purchase.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual((self.purchase.status, document.status),
                         (DocumentStatus.CONFIRMED, DocumentStatus.CONFIRMED))
        self.assertEqual(self.stock().quantity, Decimal("7"))
        self.assertFalse(movements(self.purchase).filter(reverses__isnull=False).exists())

    def test_cancelled_return_allows_purchase_cancel(self):
        document = self.confirm_return(self.make_return())
        original_return = movements(document, MovementType.RETURN_OUT).get()
        original_purchase = movements(self.purchase, MovementType.PURCHASE).get()
        self.cancel_return(document)
        CancelPurchase.execute(purchase_id=self.purchase.pk, user=None)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, DocumentStatus.CANCELLED)
        self.assertEqual(self.stock().quantity, Decimal("0"))
        self.assert_reversal(document, original_return, MovementType.RETURN_IN)
        self.assert_reversal(self.purchase, original_purchase, MovementType.RETURN_OUT)
        self.assertEqual(StockMovement.objects.count(), 4)

    def test_complete_operational_sequence_restores_initial_stock(self):
        return_api()
        # Otro producto evita mezclar el stock de la compra del setUp.
        initial = Decimal("4")
        Stock.objects.create(company=self.company, branch=self.branch, warehouse=self.warehouse,
                             product=self.product2, quantity=initial)
        purchase = self.make_purchase(lines=[PurchaseDetailDTO(
            self.product2.pk, Decimal("10"), Decimal("12"))])
        self.assertEqual(self.stock(self.product2).quantity, initial + 10)
        document = self.confirm_return(self.make_return("3", purchase=purchase))
        self.assertEqual(self.stock(self.product2).quantity, initial + 7)
        self.assert_rejected_unchanged(lambda: CancelPurchase.execute(purchase_id=purchase.pk, user=None))
        self.assertEqual(self.stock(self.product2).quantity, initial + 7)
        original_return = movements(document, MovementType.RETURN_OUT).get()
        self.cancel_return(document)
        self.assertEqual(self.stock(self.product2).quantity, initial + 10)
        self.assert_reversal(document, original_return, MovementType.RETURN_IN)
        original_purchase = movements(purchase, MovementType.PURCHASE).get()
        CancelPurchase.execute(purchase_id=purchase.pk, user=None)
        self.assertEqual(self.stock(self.product2).quantity, initial)
        self.assert_reversal(purchase, original_purchase, MovementType.RETURN_OUT)
        self.assertIsNone(original_purchase.reverses_id)
        self.assertIsNone(original_return.reverses_id)
        self.assertEqual(movements(purchase).count(), 2)
        self.assertEqual(movements(document).count(), 2)


class PurchaseReturnFixtureVerificationTests(PurchaseReturnFixture, TestCase):
    def test_existing_purchase_api_persists_nonzero_tax_fixture_and_real_cost_history(self):
        purchase = self.monetary_purchase()
        detail = purchase.details.get()
        self.assertEqual(purchase.status, DocumentStatus.CONFIRMED)
        self.assertTrue(purchase.number)
        self.assertEqual((detail.quantity, detail.unit_price), (Decimal("3"), Decimal("0.34")))
        self.assertEqual(tuple(getattr(detail, field) for field in MONEY_FIELDS),
                         (Decimal("0.01"), Decimal("1.01"), Decimal("0.01"), Decimal("1.02")))
        self.assertEqual((purchase.subtotal, purchase.tax, purchase.total),
                         (Decimal("1.01"), Decimal("0.01"), Decimal("1.02")))
        movement = movements(purchase, MovementType.PURCHASE).get()
        self.assertEqual((movement.quantity, movement.unit_cost, movement.document, movement.reverses_id),
                         (Decimal("3"), Decimal("0.34"), purchase, None))
        self.assertEqual(self.stock().quantity, Decimal("13"))

    def test_existing_purchase_api_persists_distinct_multiline_and_ambiguous_product_history(self):
        purchase = self.two_line_purchase()
        self.assertEqual(purchase.details.count(), 2)
        self.assertEqual(set(movements(purchase).values_list("product_id", "unit_cost")),
                         {(self.product.pk, Decimal("10")), (self.product2.pk, Decimal("12"))})
        ambiguous = self.make_purchase(lines=[
            PurchaseDetailDTO(self.product.pk, Decimal("5"), Decimal("10")),
            PurchaseDetailDTO(self.product.pk, Decimal("5"), Decimal("20")),
        ])
        self.assertEqual(ambiguous.details.count(), 2)
        self.assertEqual(list(movements(ambiguous).values_list("unit_cost", flat=True)),
                         [Decimal("10"), Decimal("20")])


class PurchaseReturnSRIBoundaryTests(PurchaseReturnFixture, TestCase):
    def test_entire_return_lifecycle_creates_no_electronic_document_xml_or_fiscal_sequence(self):
        from sri.models import ElectronicDocument, FiscalSequence

        return_api()
        self.assertFalse(DocumentType.objects.get(code=DocumentTypeCodes.PURCHASE_RETURN).can_issue_electronic)
        before_documents = list(ElectronicDocument.objects.order_by("pk").values())
        before_sequences = list(FiscalSequence.objects.order_by("pk").values())
        document = self.make_return()
        self.confirm_return(document)
        self.cancel_return(document)
        self.assertEqual(list(ElectronicDocument.objects.order_by("pk").values()), before_documents)
        self.assertEqual(list(FiscalSequence.objects.order_by("pk").values()), before_sequences)


class PurchaseReturnManifestTests(PurchaseReturnFixture, TestCase):
    """Manifiesto local de originales; corrupción explícita solo en fixtures.

    No impone overrides save/delete: la inmutabilidad cubre el lifecycle
    productivo y PROTECT. QuerySet.update/delete se usa aquí deliberadamente
    fuera de ese camino para construir estados históricos inconsistentes.
    """

    @staticmethod
    def manifest_model():
        from purchases.models.purchase_return_movement import PurchaseReturnMovement
        return PurchaseReturnMovement

    def manifest_rows(self, document):
        return list(self.manifest_model().objects.filter(
            purchase_return=document).order_by("pk").values())

    def original_ids(self, document):
        return set(movements(document, MovementType.RETURN_OUT).filter(
            reverses__isnull=True).values_list("pk", flat=True))

    def manifest_movement_ids(self, document):
        return set(self.manifest_model().objects.filter(
            purchase_return=document).values_list("stock_movement_id", flat=True))

    def multiline_return(self):
        _, Line, *_ = return_api()
        purchase = self.two_line_purchase()
        return self.make_return(purchase=purchase, details=[
            Line(detail.pk, Decimal("3")) for detail in purchase.details.order_by("line")])

    def assert_exact_manifest(self, document, count):
        entries = list(self.manifest_model().objects.filter(
            purchase_return=document).select_related("stock_movement"))
        actual = self.original_ids(document)
        self.assertEqual(len(entries), count)
        self.assertEqual(len(actual), count)
        self.assertEqual({entry.stock_movement_id for entry in entries}, actual)
        for entry in entries:
            self.assertEqual(entry.purchase_return_id, document.pk)
            self.assertEqual(entry.stock_movement.document, document)
            self.assertEqual(entry.stock_movement.movement_type, MovementType.RETURN_OUT)
            self.assertIsNone(entry.stock_movement.reverses_id)
        return actual

    def assert_manifest_cancellation_rejected(self, document):
        # persisted_state() anterior cubre stock, snapshots, Sequence y auditoría.
        # Se añade el manifiesto entero, incluidos otros Returns, sin tocar helpers previos.
        Manifest = self.manifest_model()
        before_manifest = list(Manifest.objects.order_by("pk").values())
        before_in = set(movements(document, MovementType.RETURN_IN).values_list("pk", flat=True))
        self.assert_rejected_unchanged(lambda: self.cancel_return(document))
        document.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.CONFIRMED)
        self.assertEqual(list(Manifest.objects.order_by("pk").values()), before_manifest)
        self.assertEqual(set(movements(document, MovementType.RETURN_IN).values_list("pk", flat=True)),
                         before_in)

    def inject_unmanifested_original(self, document, template):
        # Historia corrupta deliberada: no ejecuta stock ni llama la API productiva.
        return StockMovement.objects.create(
            company_id=template.company_id, branch_id=template.branch_id,
            warehouse_id=template.warehouse_id, product_id=template.product_id,
            quantity=template.quantity, unit_cost=template.unit_cost,
            content_type_id=template.content_type_id, object_id=document.pk,
            movement_type=MovementType.RETURN_OUT, reverses=None,
            notes="C03 TEST: original extra sin manifestar")

    def test_manifest_model_is_local_minimal_and_has_protected_relations(self):
        Manifest = self.manifest_model()
        from django.contrib.contenttypes.fields import GenericForeignKey
        from core.models.base import BaseModel

        Return, _ = return_models()
        self.assertEqual(Manifest._meta.app_label, "purchases")
        self.assertTrue(Manifest.__module__.startswith("purchases.models."))
        parent = Manifest._meta.get_field("purchase_return")
        movement = Manifest._meta.get_field("stock_movement")
        self.assertIsInstance(parent, models.ForeignKey)
        self.assertFalse(parent.one_to_one)
        self.assertIs(parent.remote_field.model, Return)
        self.assertIs(parent.remote_field.on_delete, models.PROTECT)
        self.assertIsInstance(movement, models.OneToOneField)
        self.assertIs(movement.remote_field.model, StockMovement)
        self.assertIs(movement.remote_field.on_delete, models.PROTECT)
        self.assertFalse(parent.null)
        self.assertFalse(movement.null)
        # Se permiten únicamente campos convencionales de la base existente.
        conventional = {field.name for field in BaseModel._meta.fields} | {"id"}
        self.assertEqual({field.name for field in Manifest._meta.fields} - conventional,
                         {"purchase_return", "stock_movement"})
        self.assertFalse(any(isinstance(field, models.JSONField) for field in Manifest._meta.fields))
        self.assertFalse(any(isinstance(field, GenericForeignKey) for field in Manifest._meta.private_fields))
        self.assertNotIn("expected_movement_count", {field.name for field in Return._meta.fields})
        self.assertTrue({"purchase_return_detail", "manifest_id", "effect_id", "document_line_id"}.isdisjoint(
            {field.name for field in StockMovement._meta.fields}))

    def test_one_movement_cannot_belong_to_two_manifest_entries_in_database(self):
        Manifest = self.manifest_model()
        document = self.confirm_return(self.make_return())
        movement_id, = self.assert_exact_manifest(document, 1)
        other = self.make_return("1")
        before = list(Manifest.objects.order_by("pk").values())
        # bulk_create prueba la UNIQUE real sin depender de validación de servicios.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Manifest.objects.bulk_create([
                Manifest(purchase_return=other, stock_movement_id=movement_id)])
        self.assertEqual(list(Manifest.objects.order_by("pk").values()), before)

    def test_draft_has_no_manifest_no_return_out_and_no_number(self):
        Manifest = self.manifest_model()
        document = self.make_return()
        self.assertEqual(document.status, DocumentStatus.DRAFT)
        self.assertEqual(document.number, "")
        self.assertFalse(Manifest.objects.filter(purchase_return=document).exists())
        self.assertFalse(movements(document).exists())

    def test_single_line_confirmation_manifests_exact_original_identity(self):
        self.manifest_model()
        document = self.confirm_return(self.make_return())
        self.assertEqual(document.status, DocumentStatus.CONFIRMED)
        self.assert_exact_manifest(document, 1)

    def test_multiline_confirmation_manifests_exact_original_id_set(self):
        self.manifest_model()
        document = self.confirm_return(self.multiline_return())
        self.assertEqual(document.status, DocumentStatus.CONFIRMED)
        self.assert_exact_manifest(document, 2)

    def test_second_line_failure_rolls_back_manifest_with_all_effects(self):
        Manifest = self.manifest_model()
        _, Line, *_ = return_api()
        purchase = self.two_line_purchase()
        document = self.make_return(purchase=purchase, details=[
            Line(detail.pk, Decimal("8")) for detail in purchase.details.order_by("line")])
        DecreaseStock().execute(company=self.company, branch=self.branch, warehouse=self.warehouse,
                                product=self.product2, quantity=Decimal("4"),
                                movement_type=MovementType.ADJUSTMENT_OUT)
        self.assertGreaterEqual(self.stock().available_quantity, Decimal("8"))
        self.assertEqual(self.stock(self.product2).available_quantity, Decimal("6"))
        sequence = self.return_sequence()
        next_number = sequence.next_number
        before_manifest = list(Manifest.objects.order_by("pk").values())
        self.assert_rejected_unchanged(lambda: self.confirm_return(document))
        document.refresh_from_db()
        sequence.refresh_from_db()
        self.assertEqual((document.status, document.number), (DocumentStatus.DRAFT, ""))
        self.assertEqual(sequence.next_number, next_number)
        self.assertFalse(movements(document).exists())
        self.assertFalse(Manifest.objects.filter(purchase_return=document).exists())
        self.assertEqual(list(Manifest.objects.order_by("pk").values()), before_manifest)

    def test_manifest_survives_mutation_and_deletion_of_all_details_then_cancels(self):
        self.manifest_model()
        document = self.confirm_return(self.multiline_return())
        expected_movements = self.assert_exact_manifest(document, 2)
        before_manifest = self.manifest_rows(document)
        expected_manifest_ids = {row["id"] for row in before_manifest}
        originals = list(movements(document, MovementType.RETURN_OUT))
        stock_before = {original.product_id: self.stock(original.product).quantity for original in originals}
        document.details.update(quantity=Decimal("9"), unit_price=Decimal("999"))
        self.assertEqual(self.manifest_rows(document), before_manifest)
        document.details.all().delete()
        self.assertFalse(document.details.exists())
        self.assertEqual(self.manifest_rows(document), before_manifest)
        self.assertEqual(self.manifest_movement_ids(document), expected_movements)
        self.cancel_return(document)
        self.assertEqual(document.status, DocumentStatus.CANCELLED)
        self.assertEqual(self.manifest_rows(document), before_manifest)
        self.assertEqual({row["id"] for row in self.manifest_rows(document)}, expected_manifest_ids)
        self.assertEqual(self.manifest_movement_ids(document), expected_movements)
        for original in originals:
            self.assert_reversal(document, original, MovementType.RETURN_IN)
            self.assertEqual(original.reversal_movements.count(), 1)
            self.assertEqual(self.stock(original.product).quantity,
                             stock_before[original.product_id] + original.quantity)
        self.assertEqual(movements(document, MovementType.RETURN_IN).count(), 2)

    def test_manifest_protects_original_stock_movement_from_normal_orm_delete(self):
        self.manifest_model()
        document = self.confirm_return(self.make_return())
        original = movements(document, MovementType.RETURN_OUT).get()
        before = persisted_state()
        before_manifest = self.manifest_rows(document)
        with self.assertRaises(ProtectedError), transaction.atomic():
            original.delete()
        self.assertTrue(StockMovement.objects.filter(pk=original.pk).exists())
        self.assertEqual(persisted_state(), before)
        self.assertEqual(self.manifest_rows(document), before_manifest)
        document.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.CONFIRMED)

    def test_manifest_protects_purchase_return_from_normal_orm_delete(self):
        self.manifest_model()
        document = self.confirm_return(self.make_return())
        before = persisted_state()
        before_manifest = self.manifest_rows(document)
        with self.assertRaises(ProtectedError), transaction.atomic():
            document.delete()
        self.assertTrue(type(document).objects.filter(pk=document.pk).exists())
        self.assertEqual(persisted_state(), before)
        self.assertEqual(self.manifest_rows(document), before_manifest)

    def test_cancellation_and_second_attempt_preserve_original_manifest(self):
        self.manifest_model()
        document = self.confirm_return(self.multiline_return())
        original_ids = self.assert_exact_manifest(document, 2)
        originals = list(movements(document, MovementType.RETURN_OUT))
        before_manifest = self.manifest_rows(document)
        number = document.number
        self.cancel_return(document)
        self.assertEqual(document.status, DocumentStatus.CANCELLED)
        self.assertEqual(document.number, number)
        self.assertEqual(self.manifest_rows(document), before_manifest)
        self.assertEqual(self.manifest_movement_ids(document), original_ids)
        for original in originals:
            self.assert_reversal(document, original, MovementType.RETURN_IN)
            self.assertEqual(original.reversal_movements.count(), 1)
        self.assertEqual(movements(document, MovementType.RETURN_IN).count(), 2)
        self.assertTrue(original_ids.isdisjoint(
            set(movements(document, MovementType.RETURN_IN).values_list("pk", flat=True))))
        before_second_attempt = persisted_state()
        with self.assertRaisesMessage(ValueError, "El documento ya fue anulado."):
            self.cancel_return(document)
        self.assertEqual(persisted_state(), before_second_attempt)
        self.assertEqual(self.manifest_rows(document), before_manifest)

    def test_extra_unmanifested_original_rejects_cancellation_without_partial_effects(self):
        self.manifest_model()
        document = self.confirm_return(self.make_return())
        expected = self.assert_exact_manifest(document, 1)
        original = movements(document, MovementType.RETURN_OUT).get()
        extra = self.inject_unmanifested_original(document, original)
        self.assertEqual(self.manifest_movement_ids(document), expected)
        self.assertEqual(self.original_ids(document), expected | {extra.pk})
        self.assertNotEqual(expected, self.original_ids(document))
        self.assertFalse(movements(document, MovementType.RETURN_IN).exists())
        self.assert_manifest_cancellation_rejected(document)

    def test_missing_manifest_entry_rejects_cancellation_without_partial_effects(self):
        Manifest = self.manifest_model()
        document = self.confirm_return(self.multiline_return())
        actual = self.assert_exact_manifest(document, 2)
        missing = movements(document, MovementType.RETURN_OUT).get(product=self.product2)
        # Corrupción de TEST: borrar el registro de enlace, no el movimiento protegido.
        # No es API productiva; no exige overrides de QuerySet.delete.
        Manifest.objects.filter(purchase_return=document, stock_movement=missing).delete()
        self.assertEqual(self.manifest_movement_ids(document), actual - {missing.pk})
        self.assertEqual(self.original_ids(document), actual)
        self.assertTrue(StockMovement.objects.filter(pk=missing.pk).exists())
        self.assertFalse(movements(document, MovementType.RETURN_IN).exists())
        self.assert_manifest_cancellation_rejected(document)

    def test_same_count_different_id_set_rejects_cancellation(self):
        self.manifest_model()
        document = self.confirm_return(self.multiline_return())
        expected = self.assert_exact_manifest(document, 2)
        displaced = movements(document, MovementType.RETURN_OUT).get(product=self.product2)
        # expected={A,B}, actual={A,C}; B sigue existiendo y manifestado.
        StockMovement.objects.filter(pk=displaced.pk).update(movement_type=MovementType.ADJUSTMENT_OUT)
        replacement = self.inject_unmanifested_original(document, displaced)
        actual = self.original_ids(document)
        self.assertEqual(self.manifest_movement_ids(document), expected)
        self.assertEqual(actual, (expected - {displaced.pk}) | {replacement.pk})
        self.assertEqual(len(expected), len(actual))
        self.assertNotEqual(expected, actual)
        self.assertFalse(movements(document, MovementType.RETURN_IN).exists())
        self.assert_manifest_cancellation_rejected(document)

    def test_incompatible_manifested_movement_is_rejected_for_each_boundary(self):
        self.manifest_model()
        document = self.confirm_return(self.make_return())
        self.assert_exact_manifest(document, 1)
        other_return = self.make_return("1")
        original = movements(document, MovementType.RETURN_OUT).get()
        original_purchase = movements(self.purchase, MovementType.PURCHASE).get()
        cases = (
            ("otro Return", {"object_id": other_return.pk}),
            ("tipo PURCHASE", {"movement_type": MovementType.PURCHASE}),
            ("movimiento reversor", {"reverses_id": original_purchase.pk}),
        )
        for label, corruption in cases:
            with self.subTest(history=label):
                # Mutación explícita de datos de TEST; la entry permanece sin reasignar.
                original_values = {field: getattr(original, field) for field in corruption}
                StockMovement.objects.filter(pk=original.pk).update(**corruption)
                self.assertEqual(self.manifest_movement_ids(document), {original.pk})
                self.assertNotEqual(self.manifest_movement_ids(document), self.original_ids(document))
                self.assertFalse(movements(document, MovementType.RETURN_IN).exists())
                self.assert_manifest_cancellation_rejected(document)
                StockMovement.objects.filter(pk=original.pk).update(**original_values)
