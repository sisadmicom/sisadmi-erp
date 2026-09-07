from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models.document_type import DocumentType
from catalog.models import Product
from core.models import Branch, Company
from core.services.document_totals_service import (
    DocumentTotalsService,
)
from inventory.models import Warehouse
from people.models import Customer, Person
from sales.models import Sale, SaleDetail


class DocumentTotalsServiceTest(TestCase):

    def setUp(self):
        self.person_company = Person.objects.create(
            identification="1799999999001",
            person_type="LEGAL",
            full_name="Empresa Test",
        )

        self.company = Company.objects.create(
            person=self.person_company,
            commercial_name="Empresa Test",
        )

        self.branch = Branch.objects.create(
            company=self.company,
            code="001",
            name="Matriz",
        )

        self.warehouse = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="BOD001",
            name="Bodega Principal",
        )

        self.person_customer = Person.objects.create(
            identification="0999999999002",
            person_type="NATURAL",
            full_name="Cliente Test",
        )

        self.customer = Customer.objects.create(
            person=self.person_customer,
        )

        self.product = Product.objects.create(
            company=self.company,
            code="P001",
            name="Producto Test",
            sale_price=Decimal("10.00"),
        )

        self.issue_date = date.today()

    def test_calculate_sale_totals_from_details(self):

        sale = Sale.objects.create(
            document_type=DocumentType.objects.get(code=Sale.DOCUMENT_TYPE_CODE),
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            customer=self.customer,
            issue_date=self.issue_date,
        )

        detail = SaleDetail.objects.create(
            sale=sale,
            line=1,
            product=self.product,
            quantity=Decimal("5"),
            unit_price=Decimal("10"),
            discount=Decimal("0"),
            tax_amount=Decimal("7.50"),
        )

        DocumentTotalsService.calculate(sale)

        sale.refresh_from_db()
        detail.refresh_from_db()

        self.assertEqual(
            detail.subtotal,
            Decimal("50.00"),
        )

        self.assertEqual(
            detail.total,
            Decimal("57.50"),
        )

        self.assertEqual(
            sale.subtotal,
            Decimal("50.00"),
        )

        self.assertEqual(
            sale.tax,
            Decimal("7.50"),
        )

        self.assertEqual(
            sale.total,
            Decimal("57.50"),
        )