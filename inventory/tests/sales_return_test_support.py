"""Fixtures C-02; imports de SalesReturn se difieren para obtener RED útil."""
from datetime import date
from decimal import Decimal
from django.test import TestCase
from catalog.models import Product
from core.models import Branch, Company, DocumentType, Sequence
from inventory.models import Stock, StockMovement, Warehouse
from people.models import Person, Customer
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.use_cases.create_sale import CreateSale
from sales.use_cases.confirm_sale import ConfirmSale

class SalesReturnFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(person=Person.objects.create(
            identification="C02-001", person_type="LEGAL", full_name="Empresa C02"))
        self.branch = Branch.objects.create(company=self.company, code="001", name="Matriz")
        self.warehouse = Warehouse.objects.create(company=self.company, branch=self.branch, code="W1", name="Principal")
        Sequence.objects.create(company=self.company, branch=self.branch,
                                document_type=DocumentType.objects.get(code="SALES_INVOICE"),
                                name="Ventas", prefix="VEN-", next_number=1)
        try:
            return_type = DocumentType.objects.get(code="SALES_RETURN")
            Sequence.objects.create(company=self.company, branch=self.branch, document_type=return_type,
                                    name="Devoluciones", prefix="DEV-", next_number=1)
        except DocumentType.DoesNotExist:
            pass
        self.customer = Customer.objects.create(person=Person.objects.create(
            identification="C02-C", person_type="NATURAL", full_name="Cliente C02"))
        self.product = Product.objects.create(company=self.company, code="P1", name="Producto")
        self.product2 = Product.objects.create(company=self.company, code="P2", name="Producto 2")
        Stock.objects.create(company=self.company, branch=self.branch, warehouse=self.warehouse,
                             product=self.product, quantity=Decimal("100"), reserved_quantity=Decimal("0"))
        self.sale = self.make_sale()
    def make_sale(self, quantity="10", unit_price="12.50"):
        sale = CreateSale.execute(SaleCreateDTO(
            company_id=self.company.pk, branch_id=self.branch.pk, customer_id=self.customer.pk,
            warehouse_id=self.warehouse.pk, issue_date=date(2026, 9, 15), notes="Venta",
            details=[SaleDetailDTO(product_id=self.product.pk, quantity=Decimal(quantity),
                                   unit_price=Decimal(unit_price), discount=Decimal("0"))]))
        ConfirmSale.execute(sale_id=sale.pk, user=None)
        return sale
    def api(self):
        from sales.dto.sales_return_create_dto import SalesReturnCreateDTO
        from sales.dto.sales_return_detail_dto import SalesReturnDetailDTO
        from sales.use_cases.create_sales_return import CreateSalesReturn
        from sales.use_cases.confirm_sales_return import ConfirmSalesReturn
        from sales.use_cases.cancel_sales_return import CancelSalesReturn
        return SalesReturnCreateDTO, SalesReturnDetailDTO, CreateSalesReturn, ConfirmSalesReturn, CancelSalesReturn
    def dto(self, quantity="3", sale_detail_id=None, notes=""):
        DTO, Line, *_ = self.api()
        return DTO(sale_id=self.sale.pk, issue_date=date(2026, 9, 15), notes=notes,
                   details=[Line(sale_detail_id=sale_detail_id or self.sale.details.first().pk,
                                 quantity=Decimal(quantity))])
