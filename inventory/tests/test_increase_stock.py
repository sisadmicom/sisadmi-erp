from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Product
from core.models import Branch, Company
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.stock import IncreaseStock
from people.models import Person


class IncreaseStockTest(TestCase):

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

    def execute(self, quantity):
        return IncreaseStock().execute(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=quantity,
            movement_type=MovementType.PURCHASE,
        )

    def test_positive_quantity_increments_stock(self):
        stock = self.execute(Decimal("10"))

        self.assertEqual(stock.quantity, Decimal("10"))

        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("10"))

    def test_positive_quantity_creates_movement(self):
        self.execute(Decimal("7"))

        movement = StockMovement.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=MovementType.PURCHASE,
        )

        self.assertEqual(movement.quantity, Decimal("7"))

    def test_zero_quantity_is_rejected_before_stock_or_movement_creation(self):
        with self.assertRaisesMessage(
            ValidationError,
            "La cantidad debe ser mayor que cero.",
        ):
            self.execute(Decimal("0"))

        self.assertEqual(Stock.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_negative_quantity_is_rejected_before_stock_or_movement_creation(self):
        with self.assertRaisesMessage(
            ValidationError,
            "La cantidad debe ser mayor que cero.",
        ):
            self.execute(Decimal("-1"))

        self.assertEqual(Stock.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)
