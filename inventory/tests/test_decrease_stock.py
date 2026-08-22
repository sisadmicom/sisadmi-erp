from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import Company, Branch
from people.models import Person
from catalog.models import Product

from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.stock import IncreaseStock, DecreaseStock


class DecreaseStockTest(TestCase):

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

        IncreaseStock().execute(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal("20"),
            movement_type=MovementType.PURCHASE,
            unit_cost=Decimal("5"),
        )

    def test_decrease_stock(self):

        DecreaseStock().execute(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal("7"),
            movement_type=MovementType.SALE,
            unit_cost=Decimal("5"),
        )

        stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            stock.quantity,
            Decimal("13"),
        )

    def test_decrease_stock_creates_movement(self):

        DecreaseStock().execute(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal("7"),
            movement_type=MovementType.SALE,
            unit_cost=Decimal("5"),
        )

        movement = StockMovement.objects.filter(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=MovementType.SALE,
        ).first()

        self.assertIsNotNone(movement)

        self.assertEqual(
            movement.quantity,
            Decimal("7"),
        )

        self.assertEqual(
            movement.unit_cost,
            Decimal("5"),
        )

    def test_decrease_stock_without_enough_stock(self):

        with self.assertRaises(ValidationError):

            DecreaseStock().execute(
                company=self.company,
                branch=self.branch,
                warehouse=self.warehouse,
                product=self.product,
                quantity=Decimal("21"),
                movement_type=MovementType.SALE,
            )

        stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            stock.quantity,
            Decimal("20"),
        )

    def test_decrease_stock_zero_quantity(self):

        with self.assertRaises(ValidationError):

            DecreaseStock().execute(
                company=self.company,
                branch=self.branch,
                warehouse=self.warehouse,
                product=self.product,
                quantity=Decimal("0"),
                movement_type=MovementType.SALE,
            )

    def test_decrease_stock_without_stock(self):

        another_product = Product.objects.create(
            company=self.company,
            code="P002",
            name="Producto Sin Stock",
        )

        with self.assertRaises(ValidationError):

            DecreaseStock().execute(
                company=self.company,
                branch=self.branch,
                warehouse=self.warehouse,
                product=another_product,
                quantity=Decimal("1"),
                movement_type=MovementType.SALE,
            )
