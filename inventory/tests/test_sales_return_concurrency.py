from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.core.exceptions import ValidationError
from core.exceptions.base import BusinessException
from inventory.tests.sales_return_test_support import SalesReturnFixture
from core.constants.document_status import DocumentStatus

REJECTIONS=(ValidationError, BusinessException, ValueError)

class SalesReturnConcurrencyTests(TransactionTestCase):
    reset_sequences = True
    def setUp(self):
        from core.models import DocumentType
        DocumentType.objects.get_or_create(code="SALES_INVOICE", defaults=dict(name="Factura",category="SALES",line_behavior="COMMERCIAL",requires_detail=True,affects_inventory=True,inventory_behavior="OUT",can_issue_electronic=True,is_active=True))
        DocumentType.objects.get_or_create(code="SALES_RETURN", defaults=dict(name="Devolución",category="SALES",line_behavior="COMMERCIAL",requires_detail=True,affects_inventory=True,inventory_behavior="IN",can_issue_electronic=False,is_active=True))
        self.make_sale = SalesReturnFixture.make_sale.__get__(self)
        self.api = SalesReturnFixture.api.__get__(self)
        self.dto = SalesReturnFixture.dto.__get__(self)
        SalesReturnFixture.setUp(self)
    def _confirm(self, pk, barrier):
        close_old_connections()
        barrier.wait()
        try:
            from sales.use_cases.confirm_sales_return import ConfirmSalesReturn
            ConfirmSalesReturn.execute(pk, user=None)
            return True
        except Exception:
            return False
        finally:
            close_old_connections()
    def test_two_drafts_of_seven_only_one_can_confirm(self):
        DTO, Line, Creator, Confirm, Cancel = self.api()
        a=Creator.execute(self.dto(quantity="7")); b=Creator.execute(self.dto(quantity="7"))
        barrier=Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda pk:self._confirm(pk,barrier), [a.pk,b.pk]))
        self.assertEqual(sum(results), 1)
        from sales.models import SalesReturn
        self.assertEqual(SalesReturn.objects.filter(sale=self.sale,status=DocumentStatus.CONFIRMED).count(),1)
    def test_double_confirm_has_one_effect(self):
        _, _, Creator, Confirm, _ = self.api()
        ret=Creator.execute(self.dto(quantity="1")); Confirm.execute(ret.pk)
        with self.assertRaises(REJECTIONS): Confirm.execute(ret.pk)
    def test_double_cancel_has_one_reversal(self):
        _, _, Creator, Confirm, Cancel = self.api()
        ret=Creator.execute(self.dto(quantity="1")); Confirm.execute(ret.pk); Cancel.execute(ret.pk)
        with self.assertRaises(REJECTIONS): Cancel.execute(ret.pk)
