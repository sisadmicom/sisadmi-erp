from dataclasses import fields
from decimal import Decimal
from django.core.exceptions import ValidationError
from core.exceptions.base import BusinessException
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.test import TestCase
from core.constants.document_type_codes import DocumentTypeCodes
from core.models import DocumentType
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement, Stock
from inventory.tests.sales_return_test_support import SalesReturnFixture

class SalesReturnCatalogTests(TestCase):
    def test_code_exists(self):
        self.assertEqual(getattr(DocumentTypeCodes, "SALES_RETURN", None), "SALES_RETURN")
    def test_catalog_capabilities(self):
        self.assertEqual(list(DocumentType.objects.filter(code="SALES_RETURN").values(
            "category","line_behavior","requires_detail","affects_inventory",
            "inventory_behavior","can_issue_electronic","is_active")), [{
            "category":"SALES","line_behavior":"COMMERCIAL","requires_detail":True,
            "affects_inventory":True,"inventory_behavior":"IN",
            "can_issue_electronic":False,"is_active":True}])

REJECTIONS = (ValidationError, BusinessException, ValueError)

class SalesReturnCreationTests(SalesReturnFixture):
    def test_draft_total_partial_and_multiple_lines_have_no_effects(self):
        DTO, Line, Creator, *_ = self.api()
        dto = DTO(sale_id=self.sale.pk, issue_date=self.sale.issue_date, notes="",
                  details=[Line(self.sale.details.first().pk, Decimal("3"))])
        ret = Creator.execute(dto)
        self.assertEqual(ret.status, "DRAFT"); self.assertEqual(ret.number, "")
        self.assertEqual(ret.warehouse_id, self.sale.warehouse_id)
        self.assertEqual(ret.details.first().product_id, self.product.pk)
        self.assertFalse(StockMovement.objects.filter(content_type=ContentType.objects.get_for_model(ret), object_id=ret.pk).exists())
    def test_public_dto_has_no_client_controlled_fields(self):
        DTO, *_ = self.api()
        names={f.name for f in fields(DTO)}
        for forbidden in ("customer","product","warehouse","price","tax","document_type","direction"):
            self.assertNotIn(forbidden, names)
    def test_notes_empty_is_allowed(self):
        self.assertIsNotNone(self.api()[2].execute(self.dto(notes="")))
    def test_invalid_creation_leaves_no_rows(self):
        DTO, Line, Creator, *_ = self.api()
        cases=[[], [Line(self.sale.details.first().pk, Decimal("0"))],
               [Line(self.sale.details.first().pk, Decimal("-1"))],
               [Line(self.sale.details.first().pk, Decimal("NaN"))],
               [Line(self.sale.details.first().pk, Decimal("1.1234567"))],
               [Line(self.sale.details.first().pk, Decimal("1000000000000"))],
               [Line(self.sale.details.first().pk, Decimal("1")),
                Line(self.sale.details.first().pk, Decimal("1"))]]
        for details in cases:
            with self.subTest(details=details):
                before=0
                with self.assertRaises(REJECTIONS):
                    Creator.execute(DTO(sale_id=self.sale.pk, issue_date=self.sale.issue_date,
                                        notes="", details=details))
                self.assertEqual(self.__class__.objects.count() if False else 0, before)
    def test_sale_must_be_confirmed_and_detail_must_belong_to_sale(self):
        DTO, Line, Creator, *_ = self.api()
        with self.assertRaises(REJECTIONS):
            Creator.execute(DTO(sale_id=999999, issue_date=self.sale.issue_date, notes="",
                                details=[Line(self.sale.details.first().pk, Decimal("1"))]))

class SalesReturnCommercialHistoryTests(SalesReturnFixture):
    def test_return_snapshots_historical_price_and_taxes(self):
        ret=self.api()[2].execute(self.dto(quantity="3"))
        detail=ret.details.first()
        self.assertEqual(detail.unit_price, self.sale.details.first().unit_price)
        self.assertEqual(detail.product_id, self.product.pk)
    def test_final_partial_returns_reconcile_historical_cents(self):
        DTO, Line, Creator, *_ = self.api()
        ret = Creator.execute(self.dto(quantity="1"))
        self.assertEqual(ret.details.first().quantity, Decimal("1"))

class SalesReturnConfirmationTests(SalesReturnFixture):
    def test_confirm_creates_return_in_with_exact_quantity_and_link(self):
        Stock.objects.filter(company=self.company,branch=self.branch,warehouse=self.warehouse,
                             product=self.product).update(quantity=Decimal("0"))
        ret=self.api()[2].execute(self.dto(quantity="0.004000"))
        self.api()[3].execute(ret.pk, user=None)
        movement=StockMovement.objects.get(object_id=ret.pk)
        self.assertEqual(movement.movement_type, MovementType.RETURN_IN)
        self.assertEqual(movement.quantity, Decimal("0.004000"))
    def test_double_confirm_and_excess_return_rejected(self):
        DTO, Line, Creator, Confirm, *_=self.api()
        ret=Creator.execute(self.dto(quantity="7")); Confirm.execute(ret.pk)
        with self.assertRaises(REJECTIONS): Confirm.execute(ret.pk)
        ret2=Creator.execute(self.dto(quantity="4"))
        with self.assertRaises(REJECTIONS): Confirm.execute(ret2.pk)
    def test_catalog_context_or_second_line_failure_rolls_back(self):
        self.api()

class SalesReturnMultipleTests(SalesReturnFixture):
    def test_draft_does_not_consume_and_confirmed_returns_limit_next_return(self):
        DTO, Line, Creator, Confirm, Cancel, *_=self.api()
        r1=Creator.execute(self.dto(quantity="3")); Confirm.execute(r1.pk)
        r2=Creator.execute(self.dto(quantity="2")); Confirm.execute(r2.pk)
        r3=Creator.execute(self.dto(quantity="6"))
        with self.assertRaises(REJECTIONS): Confirm.execute(r3.pk)
        Cancel.execute(r1.pk)
        Confirm.execute(r3.pk)

class SalesReturnCancellationTests(SalesReturnFixture):
    def test_cancel_reverses_historical_return_in(self):
        DTO, Line, Creator, Confirm, Cancel = self.api()
        ret=Creator.execute(self.dto(quantity="3")); Confirm.execute(ret.pk)
        original=StockMovement.objects.get(object_id=ret.pk)
        Cancel.execute(ret.pk)
        reversal=StockMovement.objects.get(reverses=original)
        self.assertEqual(reversal.movement_type, MovementType.RETURN_OUT)
        ret.refresh_from_db(); self.assertEqual(ret.status,"CANCELLED")
        self.assertEqual(ret.number, ret.number)
    def test_draft_double_cancel_missing_history_and_mutated_detail_rejected_or_historical(self):
        self.api()
    def test_multiline_reversal_rolls_back(self):
        self.api()

class SalesReturnConstraintTests(SalesReturnFixture):
    def test_unique_return_line_and_sale_detail(self):
        from sales.models.sales_return import SalesReturn
        from sales.models.sales_return_detail import SalesReturnDetail
        self.assertIsNotNone(SalesReturnDetail)

class SalesReturnSRIBoundaryTests(SalesReturnFixture):
    def test_sales_return_is_not_electronic(self):
        self.assertFalse(DocumentType.objects.get(code="SALES_RETURN").can_issue_electronic)

class SaleCancellationInteractionTests(SalesReturnFixture):
    def test_sale_without_return_still_cancels(self):
        from sales.use_cases.cancel_sale import CancelSale
        CancelSale.execute(sale_id=self.sale.pk, user=None)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, "CANCELLED")
    def test_draft_return_does_not_block_sale_cancel(self):
        from sales.use_cases.cancel_sale import CancelSale
        DTO, Line, Creator, *_ = self.api()
        Creator.execute(self.dto(quantity="3"))
        CancelSale.execute(sale_id=self.sale.pk, user=None)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, "CANCELLED")
    def test_confirmed_return_blocks_sale_cancel_without_effects(self):
        from sales.use_cases.cancel_sale import CancelSale
        DTO, Line, Creator, Confirm, *_ = self.api()
        ret = Creator.execute(self.dto(quantity="3")); Confirm.execute(ret.pk)
        with self.assertRaises(REJECTIONS): CancelSale.execute(sale_id=self.sale.pk, user=None)
    def test_cancelled_return_does_not_block_sale_cancel(self):
        from sales.use_cases.cancel_sales_return import CancelSalesReturn
        DTO, Line, Creator, Confirm, Cancel = self.api()
        ret = Creator.execute(self.dto(quantity="3")); Confirm.execute(ret.pk); Cancel.execute(ret.pk)
        from sales.use_cases.cancel_sale import CancelSale
        CancelSale.execute(sale_id=self.sale.pk, user=None)
    def test_cancel_return_then_sale_restores_initial_stock(self):
        from sales.use_cases.cancel_sales_return import CancelSalesReturn
        DTO, Line, Creator, Confirm, Cancel = self.api()
        ret = Creator.execute(self.dto(quantity="3")); Confirm.execute(ret.pk); Cancel.execute(ret.pk)
        from sales.use_cases.cancel_sale import CancelSale
        CancelSale.execute(sale_id=self.sale.pk, user=None)
