from decimal import Decimal
from datetime import date

from django.test import TestCase

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.models import Company, Branch, Sequence
from catalog.models import Product
from people.models import Person, Supplier

from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.kardex.kardex_service import KardexService
from inventory.constants.movement_type import MovementType

from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.use_cases.create_purchase import CreatePurchase
from purchases.use_cases.confirm_purchase import ConfirmPurchase


class PurchaseInventoryReceiptTest(TestCase):

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

        Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            document_type=DocumentType.objects.get(code=DocumentTypeCodes.PURCHASE_INVOICE),
            code="CUSTOM-PUR",
            name="Compras",
            prefix="OC-",
            series="001",
            next_number=1,
            padding=6,
        )

    def create_purchase(
        self,
        quantity="5",
        unit_price="10",
    ):

        dto = PurchaseCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            supplier_id=self.supplier.id,
            issue_date=date.today(),
            notes="Compra de prueba",
            details=[
                PurchaseDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal(quantity),
                    unit_price=Decimal(unit_price),
                )
            ],
        )

        return CreatePurchase.execute(dto)

    def test_confirm_purchase_increases_stock(self):

        purchase = self.create_purchase("5", "10")

        ConfirmPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            stock.quantity,
            Decimal("5"),
        )

    def test_confirm_purchase_creates_stock_movement(self):

        purchase = self.create_purchase("5", "10")

        ConfirmPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        movement = StockMovement.objects.get(
            content_type__model="purchase",
            object_id=purchase.id,
        )

        self.assertEqual(
            movement.movement_type,
            MovementType.PURCHASE,
        )

        self.assertEqual(
            movement.quantity,
            Decimal("5"),
        )

        self.assertEqual(
            movement.unit_cost,
            Decimal("10"),
        )

        self.assertEqual(
            movement.product,
            self.product,
        )

        self.assertEqual(
            movement.warehouse,
            self.warehouse,
        )

    def test_confirm_purchase_updates_kardex(self):

        purchase = self.create_purchase(
            quantity="5",
            unit_price="10",
        )

        ConfirmPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

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
            movement.quantity_in,
            Decimal("5"),
        )

        self.assertEqual(
            movement.quantity_out,
            Decimal("0"),
        )

        self.assertEqual(
            movement.balance,
            Decimal("5"),
        )

    def test_confirm_purchase_associates_movement_to_document(
        self,
    ):

        purchase = self.create_purchase("5", "10")

        purchase = ConfirmPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        movement = StockMovement.objects.get(
            content_type__model="purchase",
            object_id=purchase.id,
        )

        self.assertEqual(
            movement.document,
            purchase,
        )

        self.assertEqual(
            movement.notes,
            f"Compra {purchase.number}",
        )

    def test_confirm_purchase_twice_does_not_duplicate_stock(
        self,
    ):

        purchase = self.create_purchase("5", "10")

        ConfirmPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        with self.assertRaises(Exception):

            ConfirmPurchase.execute(
                purchase_id=purchase.id,
                user=None,
            )

        stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            stock.quantity,
            Decimal("5"),
        )

        self.assertEqual(
            StockMovement.objects.count(),
            1,
        )

    def test_purchase_without_details_does_not_change_inventory(
        self,
    ):

        purchase = self.create_purchase("5", "10")

        purchase.details.all().delete()

        with self.assertRaises(Exception):

            ConfirmPurchase.execute(
                purchase_id=purchase.id,
                user=None,
            )

        self.assertEqual(
            Stock.objects.count(),
            0,
        )

        self.assertEqual(
            StockMovement.objects.count(),
            0,
        )