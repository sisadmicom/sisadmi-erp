from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.document_status import DocumentStatus
from core.models import Company, Branch, Sequence
from catalog.models import Product
from people.models import Person, Supplier

from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.kardex.kardex_service import KardexService

from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.use_cases.create_purchase import CreatePurchase
from purchases.use_cases.confirm_purchase import ConfirmPurchase
from purchases.use_cases.cancel_purchase import CancelPurchase


class CancelPurchaseTest(TestCase):

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

    def test_cancel_confirmed_purchase(self):

        purchase = self.create_purchase("5")

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

        CancelPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        purchase.refresh_from_db()
        stock.refresh_from_db()

        self.assertEqual(
            purchase.status,
            DocumentStatus.CANCELLED,
        )

        self.assertEqual(
            stock.quantity,
            Decimal("0"),
        )

    def test_cancel_purchase_creates_return_out_movement(self):

        purchase = self.create_purchase("5", "10")

        ConfirmPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        purchase.refresh_from_db()

        CancelPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        movements = StockMovement.objects.filter(
            content_type__model="purchase",
            object_id=purchase.id,
        ).order_by("id")

        self.assertEqual(
            movements.count(),
            2,
        )

        movement = movements.last()

        self.assertEqual(
            movement.movement_type,
            MovementType.RETURN_OUT,
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
            movement.document,
            purchase,
        )

        self.assertEqual(
            movement.notes,
            f"Anulación compra {purchase.number}",
        )

    def test_cancel_purchase_updates_kardex(self):

        purchase = self.create_purchase("5")

        ConfirmPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        CancelPurchase.execute(
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
            2,
        )

        self.assertEqual(
            kardex[0].quantity_in,
            Decimal("5"),
        )

        self.assertEqual(
            kardex[0].quantity_out,
            Decimal("0"),
        )

        self.assertEqual(
            kardex[0].balance,
            Decimal("5"),
        )

        self.assertEqual(
            kardex[1].quantity_in,
            Decimal("0"),
        )

        self.assertEqual(
            kardex[1].quantity_out,
            Decimal("5"),
        )

        self.assertEqual(
            kardex[1].balance,
            Decimal("0"),
        )

    def test_cancel_purchase_twice_fails(self):

        purchase = self.create_purchase("5")

        ConfirmPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        CancelPurchase.execute(
            purchase_id=purchase.id,
            user=None,
        )

        with self.assertRaisesMessage(
            ValueError,
            "El documento ya fue anulado.",
        ):
            CancelPurchase.execute(
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
            Decimal("0"),
        )

        self.assertEqual(
            StockMovement.objects.count(),
            2,
        )

    def test_cancel_draft_purchase_fails(self):

        purchase = self.create_purchase("5")

        with self.assertRaisesMessage(
            ValueError,
            "Solo se pueden anular documentos confirmados.",
        ):
            CancelPurchase.execute(
                purchase_id=purchase.id,
                user=None,
            )

        self.assertEqual(
            purchase.status,
            DocumentStatus.DRAFT,
        )

        self.assertEqual(
            Stock.objects.count(),
            0,
        )

        self.assertEqual(
            StockMovement.objects.count(),
            0,
        )

    def test_cancel_without_stock_rolls_back(self):

        purchase = self.create_purchase("5")

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

        stock.quantity = Decimal("0")
        stock.save(
            update_fields=["quantity"]
        )

        with self.assertRaises(ValidationError):

            CancelPurchase.execute(
                purchase_id=purchase.id,
                user=None,
            )

        purchase.refresh_from_db()
        stock.refresh_from_db()

        self.assertEqual(
            purchase.status,
            DocumentStatus.CONFIRMED,
        )

        self.assertEqual(
            stock.quantity,
            Decimal("0"),
        )

        self.assertEqual(
            StockMovement.objects.count(),
            1,
        )