from decimal import Decimal

from django.test import TestCase

from core.models import Company, Branch
from people.models import Person, Customer
from catalog.models import Product, Tax
from inventory.models import Warehouse

from sales.models import Sale, SaleDetail, SaleDetailTax


class SaleDetailTaxTest(TestCase):

    def setUp(self):

        company_person = Person.objects.create(
            identification="1790000002001",
            person_type="LEGAL",
            full_name="Empresa Tax Detail Test",
        )

        self.company = Company.objects.create(
            person=company_person,
            commercial_name="Empresa Tax Detail Test",
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
            identification="0911111112001",
            person_type="NATURAL",
            full_name="Cliente Tax Detail Test",
        )

        self.customer = Customer.objects.create(
            person=customer_person,
        )

        self.product = Product.objects.create(
            company=self.company,
            code="P001",
            name="Producto Tax Test",
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

        self.sale = Sale.objects.create(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            customer=self.customer,
        )

        self.detail = SaleDetail.objects.create(
            sale=self.sale,
            line=1,
            product=self.product,
            quantity=Decimal("5"),
            unit_price=Decimal("20"),
            discount=Decimal("0"),
            subtotal=Decimal("100.00"),
        )

    def test_create_sale_detail_tax(self):

        applied_tax = SaleDetailTax.objects.create(
            detail=self.detail,
            tax=self.iva,
            tax_code=self.iva.code,
            tax_name=self.iva.name,
            tax_type=self.iva.tax_type,
            rate=self.iva.rate,
            base=Decimal("100.00"),
            amount=Decimal("15.00"),
        )

        self.assertEqual(
            applied_tax.detail,
            self.detail,
        )

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
            Decimal("100.00"),
        )

        self.assertEqual(
            applied_tax.amount,
            Decimal("15.00"),
        )

    def test_detail_can_have_multiple_taxes(self):

        SaleDetailTax.objects.create(
            detail=self.detail,
            tax=self.iva,
            tax_code=self.iva.code,
            tax_name=self.iva.name,
            tax_type=self.iva.tax_type,
            rate=self.iva.rate,
            base=Decimal("100.00"),
            amount=Decimal("15.00"),
        )

        SaleDetailTax.objects.create(
            detail=self.detail,
            tax=self.ice,
            tax_code=self.ice.code,
            tax_name=self.ice.name,
            tax_type=self.ice.tax_type,
            rate=self.ice.rate,
            base=Decimal("100.00"),
            amount=Decimal("10.00"),
        )

        taxes = self.detail.applied_taxes.all()

        self.assertEqual(
            taxes.count(),
            2,
        )

        self.assertEqual(
            taxes.filter(tax=self.iva).count(),
            1,
        )

        self.assertEqual(
            taxes.filter(tax=self.ice).count(),
            1,
        )

        self.assertEqual(
            sum(
                tax.amount
                for tax in taxes
            ),
            Decimal("25.00"),
        )
