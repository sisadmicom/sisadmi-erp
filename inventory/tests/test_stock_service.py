from decimal import Decimal

from django.test import TestCase

from core.models import Company, Branch
from people.models import Person
from catalog.models import Product

from inventory.models import Stock
from inventory.models import Warehouse

from inventory.services import IncreaseStock
from inventory.services import DecreaseStock

from inventory.constants.movement_type import MovementType


class StockServiceTest(TestCase):

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

        self.product = Product.objects.create(
            company=self.company,
            code="P001",
            name="Producto Test",
        )

    def test_create_stock_if_not_exists(self):

        stock = IncreaseStock().execute(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal("10"),
            movement_type=MovementType.PURCHASE,
        )

        self.assertEqual(stock.quantity, Decimal("10"))

    def test_increase_existing_stock(self):

        IncreaseStock().execute(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal("10"),
            movement_type=MovementType.PURCHASE,
        )

        stock = IncreaseStock().execute(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal("5"),
            movement_type=MovementType.PURCHASE,
        )

        self.assertEqual(stock.quantity, Decimal("15"))

    def test_only_one_stock_record_exists(self):

        IncreaseStock().execute(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal("10"),
            movement_type=MovementType.PURCHASE,
        )

        IncreaseStock().execute(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal("5"),
            movement_type=MovementType.PURCHASE,
        )

        self.assertEqual(
            Stock.objects.count(),
            1,
        )

        stock = Stock.objects.first()

        self.assertEqual(
            stock.quantity,
            Decimal("15"),
        )