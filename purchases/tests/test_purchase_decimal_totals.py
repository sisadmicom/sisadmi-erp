"""Explicit draft recalculation must preserve the creation rounding policy."""
from datetime import date
from decimal import Decimal, ROUND_DOWN, localcontext

from django.test import TestCase

from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.services.purchase_creator import PurchaseCreator
from purchases.services.purchase_service import PurchaseService
from purchases.tests import test_create_purchase as fixtures


class PurchaseDecimalTotalsTests(TestCase):
    def setUp(self):
        fixtures.CreatePurchaseTest.setUp(self)

    def test_recalculation_keeps_half_cent_lines_and_header_consistent(self):
        purchase = PurchaseCreator.create(PurchaseCreateDTO(
            company_id=self.company.pk, branch_id=self.branch.pk,
            supplier_id=self.supplier.pk, issue_date=date(2026, 1, 1), notes='',
            details=[PurchaseDetailDTO(product_id=self.product.pk, quantity=Decimal('1'),
                unit_price=Decimal('0.005000'), discount=Decimal('0')) for _ in range(2)]))
        with localcontext() as ctx:
            ctx.rounding = ROUND_DOWN
            PurchaseService.calculate(purchase)
        self.assertEqual(purchase.subtotal, Decimal('0.02'))
        self.assertEqual(purchase.total, Decimal('0.02'))
        self.assertEqual(list(purchase.details.values_list('subtotal', flat=True)),
                         [Decimal('0.01'), Decimal('0.01')])
