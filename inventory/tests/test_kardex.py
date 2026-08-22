from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Company, Branch, Sequence
from core.constants.movement_types import MovementTypes

from people.models import Person, Supplier
from catalog.models import Product

from inventory.services.kardex import KardexService

from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO

from purchases.use_cases.create_purchase import CreatePurchase
from purchases.use_cases.confirm_purchase import ConfirmPurchase

from inventory.models import Warehouse

class KardexServiceTest(TestCase):

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

    def create_purchase(self, quantity):

        dto = PurchaseCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            supplier_id=self.supplier.id,
            issue_date=date.today(),
            notes="Compra",
            details=[
                PurchaseDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal(quantity),
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

        return purchase

    def test_empty_kardex(self):

        kardex = KardexService.get_product(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            len(kardex),
            0,
        )

    def test_kardex_after_purchase(self):

        self.create_purchase("10")

        kardex = KardexService.get_product(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            len(kardex),
            1,
        )

        movement = kardex[0]

        self.assertEqual(
            movement.movement_type,
            "Compra",
        )

        self.assertEqual(
            movement.quantity_in,
            Decimal("10"),
        )

        self.assertEqual(
            movement.balance,
            Decimal("10"),
        )

    def test_kardex_multiple_purchases(self):

        self.create_purchase("10")
        self.create_purchase("5")

        kardex = KardexService.get_product(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            len(kardex),
            2,
        )

        self.assertEqual(
            kardex[0].balance,
            Decimal("10"),
        )

        self.assertEqual(
            kardex[1].balance,
            Decimal("15"),
        )

    def test_kardex_is_ordered(self):

        self.create_purchase("10")
        self.create_purchase("5")

        kardex = KardexService.get_product(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertLess(
            kardex[0].movement_date,
            kardex[1].movement_date,
        )