from decimal import Decimal

from django.db.models.deletion import ProtectedError
from django.test import TestCase

from catalog.models import Product
from core.models import Branch, Company
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement, Warehouse
from inventory.services.movement.create_stock_movement import CreateStockMovement
from people.models import Person


class StockMovementReversesTest(TestCase):

    def setUp(self):
        person = Person.objects.create(
            identification="1790000001001",
            person_type="LEGAL",
            full_name="Empresa Test",
        )
        self.company = Company.objects.create(
            person=person,
            commercial_name="Empresa Test",
        )
        self.branch = Branch.objects.create(
            company=self.company, code="001", name="Matriz",
        )
        self.warehouse = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="BOD001",
            name="Principal",
        )
        self.product = Product.objects.create(
            company=self.company, code="P001", name="Producto Test",
        )

    def create_movement(self, **kwargs):
        return CreateStockMovement().execute(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=MovementType.ADJUSTMENT_IN,
            quantity=Decimal("1"),
            **kwargs,
        )

    def test_normal_movement_has_no_reverses(self):
        movement = self.create_movement()

        self.assertIsInstance(movement, StockMovement)
        movement.refresh_from_db()
        self.assertIsNone(movement.reverses)

    def test_compensatory_movement_persists_original_reference(self):
        original = self.create_movement()
        reversal = self.create_movement(reverses=original)

        self.assertIsInstance(reversal, StockMovement)
        reversal.refresh_from_db()
        self.assertEqual(reversal.reverses, original)

    def test_original_exposes_multiple_reversal_movements(self):
        original = self.create_movement()
        reversal = self.create_movement(reverses=original)
        another_reversal = self.create_movement(reverses=original)

        self.assertCountEqual(
            original.reversal_movements.all(),
            [reversal, another_reversal],
        )

    def test_original_is_protected_from_physical_deletion(self):
        original = self.create_movement()
        reversal = self.create_movement(reverses=original)
        original_id = original.pk

        with self.assertRaises(ProtectedError) as error:
            original.delete()

        self.assertIn(reversal, error.exception.protected_objects)
        self.assertTrue(StockMovement.objects.filter(pk=original_id).exists())
        reversal.refresh_from_db()
        self.assertEqual(reversal.reverses_id, original_id)
