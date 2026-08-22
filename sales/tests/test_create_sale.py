from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Company, Branch
from people.models import Person, Customer
from catalog.models import Product
from inventory.models import Warehouse

from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO

from sales.use_cases.create_sale import CreateSale

from core.constants.document_status import DocumentStatus
from catalog.models import Tax
from catalog.models import TaxConfiguration

from catalog.models import (
    Product,
    Tax,
    TaxConfiguration,
)

from sales.models import SaleDetailTax

class CreateSaleTest(TestCase):

    def setUp(self):

        company_person = Person.objects.create(
            identification="1790000001001",
            person_type="LEGAL",
            full_name="Empresa Test",
        )

        self.company = Company.objects.create(
            person=company_person,
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
            name="Principal",
            is_main=True,
        )

        customer_person = Person.objects.create(
            identification="0911111111001",
            person_type="NATURAL",
            full_name="Cliente Test",
        )

        self.customer = Customer.objects.create(
            person=customer_person,
        )

        self.product = Product.objects.create(
            company=self.company,
            code="P001",
            name="Producto Test",
        )

        self.iva = Tax.objects.create(
            company=self.company,
            name="IVA 15%",
            code="IVA15",
            tax_type="IVA",
            rate=Decimal("15.0000"),
        )

        self.ice = Tax.objects.create(
            company=self.company,
            name="ICE 10%",
            code="ICE10",
            tax_type="ICE",
            rate=Decimal("10.0000"),
        )

        self.tax_configuration = TaxConfiguration.objects.create(
            company=self.company,
        )

        self.tax_configuration.taxes.add(
            self.iva
        )

    def test_create_sale(self):

        dto = SaleCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            customer_id=self.customer.id,
            issue_date=date(2025, 1, 1),
            notes="Venta de prueba",
            details=[
                SaleDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("5"),
                    unit_price=Decimal("10"),
                    discount=Decimal("0"),
                )
            ],
        )

        sale = CreateSale.execute(dto)

        self.assertEqual(
            sale.customer,
            self.customer,
        )

        self.assertEqual(
            sale.warehouse,
            self.warehouse,
        )

        self.assertEqual(
            sale.status,
            DocumentStatus.DRAFT,
        )

        self.assertEqual(
            sale.number,
            "",
        )

        self.assertEqual(
            sale.details.count(),
            1,
        )

        self.assertEqual(
            sale.subtotal,
            Decimal("50"),
        )

        self.assertEqual(
            sale.tax,
            Decimal("7.50"),
        )

        self.assertEqual(
            sale.total,
            Decimal("57.50"),
        )

    def test_create_sale_applies_global_tax(self):

        dto = SaleCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            customer_id=self.customer.id,
            issue_date=date(2025, 1, 1),
            notes="Venta con impuesto global",
            details=[
                SaleDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("5"),
                    unit_price=Decimal("10"),
                    discount=Decimal("0"),
                )
            ],
        )

        sale = CreateSale.execute(dto)

        detail = sale.details.first()

        applied_taxes = detail.applied_taxes.all()

        self.assertEqual(
            applied_taxes.count(),
            1,
        )

        applied_tax = applied_taxes.first()

        self.assertEqual(
            applied_tax.tax,
            self.iva,
        )

        self.assertEqual(
            applied_tax.tax_code,
            "IVA15",
        )

        self.assertEqual(
            applied_tax.tax_type,
            "IVA",
        )

        self.assertEqual(
            applied_tax.rate,
            Decimal("15.0000"),
        )

        self.assertEqual(
            applied_tax.base,
            Decimal("50.00"),
        )

        self.assertEqual(
            applied_tax.amount,
            Decimal("7.50"),
        )

        self.assertEqual(
            detail.subtotal,
            Decimal("50.00"),
        )

        self.assertEqual(
            detail.tax_amount,
            Decimal("7.50"),
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

    def test_create_sale_with_discount_and_tax(self):

        dto = SaleCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            customer_id=self.customer.id,
            issue_date=date(2025, 1, 1),
            notes="Venta con descuento",
            details=[
                SaleDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("5"),
                    unit_price=Decimal("10"),
                    discount=Decimal("5"),
                )
            ],
        )

        sale = CreateSale.execute(dto)

        detail = sale.details.first()

        self.assertEqual(
            detail.subtotal,
            Decimal("45.00"),
        )

        self.assertEqual(
            detail.tax_amount,
            Decimal("6.75"),
        )

        self.assertEqual(
            detail.total,
            Decimal("51.75"),
        )

        self.assertEqual(
            sale.subtotal,
            Decimal("45.00"),
        )

        self.assertEqual(
            sale.tax,
            Decimal("6.75"),
        )

        self.assertEqual(
            sale.total,
            Decimal("51.75"),
        )