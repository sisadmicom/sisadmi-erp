from decimal import Decimal
from datetime import date

from django.contrib.contenttypes.models import ContentType

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.document_status import DocumentStatus
from core.models import Company, Branch, Sequence
from core.exceptions.inventory import InventoryException
from catalog.models import Product
from people.models import Person, Supplier

from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.kardex.kardex_service import KardexService
from inventory.services.stock import DecreaseStock

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
            f"Reversión del movimiento {movement.reverses_id}",
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

    def original_movements(self, purchase):
        return StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(purchase),
            object_id=purchase.pk,
            movement_type=MovementType.PURCHASE,
            reverses__isnull=True,
        ).order_by("id")

    def assert_historical_reversal(self, purchase, original):
        reversal = original.reversal_movements.get()
        self.assertEqual(reversal.movement_type, MovementType.RETURN_OUT)
        self.assertEqual(reversal.reverses, original)
        self.assertEqual(reversal.document, purchase)
        for field in (
            "quantity", "unit_cost", "company_id", "branch_id",
            "warehouse_id", "product_id",
        ):
            self.assertEqual(getattr(reversal, field), getattr(original, field), field)
        return reversal

    def test_cancel_preserves_historical_movement_and_traceability(self):
        purchase = self.create_purchase("5", "10")
        ConfirmPurchase.execute(purchase_id=purchase.pk, user=None)
        original = self.original_movements(purchase).get()
        CancelPurchase.execute(purchase_id=purchase.pk)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, DocumentStatus.CANCELLED)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("0"))
        self.assert_historical_reversal(purchase, original)
        self.assertEqual(original.reversal_movements.count(), 1)

    def test_cancel_uses_history_after_detail_quantity_and_price_change(self):
        purchase = self.create_purchase("10", "5")
        ConfirmPurchase.execute(purchase_id=purchase.pk, user=None)
        original = self.original_movements(purchase).get()
        purchase.details.update(quantity=Decimal("6"), unit_price=Decimal("99"))
        CancelPurchase.execute(purchase_id=purchase.pk)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("0"))
        reversal = self.assert_historical_reversal(purchase, original)
        self.assertEqual(reversal.quantity, Decimal("10"))
        self.assertEqual(reversal.unit_cost, Decimal("5"))

    def test_cancel_succeeds_after_details_are_deleted(self):
        purchase = self.create_purchase("5", "10")
        ConfirmPurchase.execute(purchase_id=purchase.pk, user=None)
        original = self.original_movements(purchase).get()
        purchase.details.all().delete()
        CancelPurchase.execute(purchase_id=purchase.pk)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, DocumentStatus.CANCELLED)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("0"))
        self.assert_historical_reversal(purchase, original)

    def test_confirmed_purchase_without_history_is_rejected(self):
        purchase = self.create_purchase("5", "10")
        ConfirmPurchase.execute(purchase_id=purchase.pk, user=None)
        self.original_movements(purchase).delete()
        with self.assertRaises(InventoryException):
            CancelPurchase.execute(purchase_id=purchase.pk)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, DocumentStatus.CONFIRMED)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("5"))
        self.assertFalse(StockMovement.objects.exists())

    def create_purchase_with_two_products(self):
        other = Product.objects.create(company=self.company, code="P002", name="Otro")
        Stock.objects.create(company=self.company, branch=self.branch,
                             warehouse=self.warehouse, product=other, quantity=Decimal("30"))
        purchase = CreatePurchase.execute(PurchaseCreateDTO(
            company_id=self.company.pk, branch_id=self.branch.pk,
            supplier_id=self.supplier.pk, issue_date=date.today(), notes="Dos productos",
            details=[
                PurchaseDetailDTO(product_id=self.product.pk, quantity=Decimal("5"), unit_price=Decimal("10")),
                PurchaseDetailDTO(product_id=other.pk, quantity=Decimal("7"), unit_price=Decimal("12")),
            ],
        ))
        ConfirmPurchase.execute(purchase_id=purchase.pk, user=None)
        return purchase, other

    def test_each_historical_movement_gets_its_own_compensation(self):
        purchase, other = self.create_purchase_with_two_products()
        originals = list(self.original_movements(purchase))
        CancelPurchase.execute(purchase_id=purchase.pk)
        for original in originals:
            self.assert_historical_reversal(purchase, original)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("0"))
        self.assertEqual(Stock.objects.get(product=other).quantity, Decimal("30"))
        self.assertEqual(StockMovement.objects.filter(reverses__isnull=False).count(), 2)

    def test_second_line_insufficient_stock_rolls_back_first_reversal(self):
        purchase, other = self.create_purchase_with_two_products()
        originals = list(self.original_movements(purchase))
        DecreaseStock().execute(company=self.company, branch=self.branch, warehouse=self.warehouse,
                                product=other, quantity=Decimal("31"), movement_type=MovementType.ADJUSTMENT_OUT)
        with self.assertRaises(ValidationError):
            CancelPurchase.execute(purchase_id=purchase.pk)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, DocumentStatus.CONFIRMED)
        self.assertIsNone(purchase.cancelled_at)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("5"))
        self.assertEqual(Stock.objects.get(product=other).quantity, Decimal("6"))
        self.assertFalse(StockMovement.objects.filter(reverses__isnull=False).exists())
        self.assertEqual(StockMovement.objects.filter(movement_type=MovementType.PURCHASE).count(), 2)
        for original in originals:
            self.assertFalse(original.reversal_movements.exists())

    def test_cancel_selects_only_original_purchase_movements(self):
        purchase = self.create_purchase("5", "10")
        ConfirmPurchase.execute(purchase_id=purchase.pk, user=None)
        original = self.original_movements(purchase).get()
        common = dict(company=self.company, branch=self.branch, warehouse=self.warehouse,
                      product=self.product, quantity=Decimal("1"))
        unrelated_type = StockMovement.objects.create(**common, movement_type=MovementType.ADJUSTMENT_IN,
            content_type=ContentType.objects.get_for_model(purchase), object_id=purchase.pk)
        unrelated_document = StockMovement.objects.create(**common, movement_type=MovementType.PURCHASE,
            content_type=ContentType.objects.get_for_model(Warehouse), object_id=purchase.pk)
        compensatory_purchase = StockMovement.objects.create(**common, movement_type=MovementType.PURCHASE,
            reverses=unrelated_document, content_type=ContentType.objects.get_for_model(purchase), object_id=purchase.pk)
        CancelPurchase.execute(purchase_id=purchase.pk)
        self.assert_historical_reversal(purchase, original)
        for movement in (unrelated_type, compensatory_purchase):
            self.assertFalse(movement.reversal_movements.exists())
        self.assertEqual(unrelated_document.reversal_movements.count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type=MovementType.RETURN_OUT).count(), 1)
