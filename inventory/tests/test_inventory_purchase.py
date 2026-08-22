from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Company, Branch, Sequence
from people.models import Person, Supplier
from catalog.models import Product
from inventory.models import Stock, Warehouse

from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO

from purchases.use_cases.create_purchase import CreatePurchase
from purchases.use_cases.confirm_purchase import ConfirmPurchase

class InventoryPurchaseTest(TestCase):


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

        Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="BOD001",
            name="Principal",
            is_main=True,
        )

        Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            code="PUR",
            name="Compras",
            prefix="COM-",
            series="001",
        )

        supplier_person = Person.objects.create(
            identification="0999999999001",
            person_type="LEGAL",
            full_name="Proveedor Test",
        )

        self.supplier = Supplier.objects.create(
            person=supplier_person,
        )

        self.product = Product.objects.create(
            company=self.company,
            code="P001",
            name="Producto Test",
        )

    def test_confirm_purchase_creates_stock(self):

        dto = PurchaseCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            supplier_id=self.supplier.id,
            issue_date=date(2025, 1, 1),
            notes="Compra",
            details=[
                PurchaseDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("10"),
                    unit_price=Decimal("5"),
                    discount=Decimal("0"),
                )
            ],
        )

        purchase = CreatePurchase.execute(dto)

        ConfirmPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            product=self.product,
        )

        self.assertEqual(
            stock.quantity,
            Decimal("10"),
        )