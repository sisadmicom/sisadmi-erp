from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType

from django.test import TestCase

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.document_status import DocumentStatus
from core.models import Branch, Company, Sequence
from core.exceptions.inventory import InventoryException

from catalog.models import Product

from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.kardex.kardex_service import KardexService
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService

from people.models import Customer, Person

from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.use_cases.create_sale import CreateSale
from sales.use_cases.confirm_sale import ConfirmSale
from sales.use_cases.cancel_sale import CancelSale


class CancelSaleTest(TestCase):

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
            document_type=DocumentType.objects.get(code=DocumentTypeCodes.SALES_INVOICE),
            name="Ventas",
            prefix="VEN-",
            series="001",
            next_number=1,
            padding=6,
        )

        customer_person = Person.objects.create(
            identification="0911111111001",
            person_type="NATURAL",
            full_name="Cliente Test",
        )

        self.customer = Customer.objects.create(
            person=customer_person,
        )

        self.product = Product.objects.create(
            company=self.company,
            code="P001",
            name="Producto Test",
        )

        Stock.objects.create(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal("20"),
            reserved_quantity=Decimal("0"),
        )

    def create_sale(self, quantity="5"):

        dto = SaleCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            customer_id=self.customer.id,
            warehouse_id=self.warehouse.id,
            issue_date=date.today(),
            notes="Venta de prueba",
            details=[
                SaleDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal(quantity),
                    unit_price=Decimal("10"),
                    discount=Decimal("0"),
                )
            ],
        )

        return CreateSale.execute(dto)

    def confirm_sale(self):

        sale = self.create_sale()

        ConfirmSale.execute(
            sale_id=sale.id,
            user=None,
        )

        sale.refresh_from_db()

        return sale

    def test_cancel_sale_changes_status(self):

        sale = self.confirm_sale()

        CancelSale.execute(
            sale_id=sale.id,
            user=None,
        )

        sale.refresh_from_db()

        self.assertEqual(
            sale.status,
            DocumentStatus.CANCELLED,
        )

    def test_cancel_sale_returns_stock(self):

        sale = self.confirm_sale()

        stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            stock.quantity,
            Decimal("15"),
        )

        CancelSale.execute(
            sale_id=sale.id,
            user=None,
        )

        stock.refresh_from_db()

        self.assertEqual(
            stock.quantity,
            Decimal("20"),
        )

    def test_cancel_sale_creates_return_in_movement(self):

        sale = self.confirm_sale()

        CancelSale.execute(
            sale_id=sale.id,
            user=None,
        )

        movement = StockMovement.objects.get(
            content_type__model="sale",
            object_id=sale.id,
            movement_type=MovementType.RETURN_IN,
        )

        self.assertEqual(
            movement.quantity,
            Decimal("5"),
        )

        self.assertEqual(
            movement.product,
            self.product,
        )

        self.assertEqual(
            movement.warehouse,
            self.warehouse,
        )

    def test_cancel_sale_associates_movement_to_document(self):

        sale = self.confirm_sale()

        CancelSale.execute(
            sale_id=sale.id,
            user=None,
        )

        movement = StockMovement.objects.get(
            content_type__model="sale",
            object_id=sale.id,
            movement_type=MovementType.RETURN_IN,
        )

        self.assertEqual(
            movement.document,
            sale,
        )

        self.assertEqual(
            movement.notes,
            f"Reversión del movimiento {movement.reverses_id}",
        )

    def test_cancel_sale_updates_kardex(self):

        StockMovement.objects.create(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=MovementType.PURCHASE,
            quantity=Decimal("20"),
            unit_cost=Decimal("5"),
            notes="Stock inicial de prueba",
        )

        sale = self.confirm_sale()

        CancelSale.execute(
            sale_id=sale.id,
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
            3,
        )

        self.assertEqual(
            kardex[0].quantity_in,
            Decimal("20"),
        )

        self.assertEqual(
            kardex[0].balance,
            Decimal("20"),
        )

        self.assertEqual(
            kardex[1].quantity_out,
            Decimal("5"),
        )

        self.assertEqual(
            kardex[1].balance,
            Decimal("15"),
        )

        self.assertEqual(
            kardex[2].quantity_in,
            Decimal("5"),
        )

        self.assertEqual(
            kardex[2].balance,
            Decimal("20"),
        )

    def test_cancel_sale_twice_fails(self):

        sale = self.confirm_sale()

        CancelSale.execute(
            sale_id=sale.id,
            user=None,
        )

        with self.assertRaisesMessage(
            ValueError,
            "El documento ya fue anulado.",
        ):
            CancelSale.execute(
                sale_id=sale.id,
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
            Decimal("20"),
        )

        self.assertEqual(
            StockMovement.objects.count(),
            2,
        )

    def test_cancel_draft_sale_uses_universal_lifecycle_error(self):

        sale = self.create_sale()

        with self.assertRaisesMessage(
            ValueError,
            "Solo se pueden anular documentos confirmados.",
        ):
            CancelSale.execute(
                sale_id=sale.id,
                user=None,
            )

        sale.refresh_from_db()
        self.assertEqual(sale.status, DocumentStatus.DRAFT)


    def original_movements(self, sale):
        return StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(sale),
            object_id=sale.pk,
            movement_type=MovementType.SALE,
            reverses__isnull=True,
        ).order_by("id")

    def assert_historical_reversal(self, sale, original):
        reversal = original.reversal_movements.get()
        self.assertEqual(reversal.movement_type, MovementType.RETURN_IN)
        self.assertEqual(reversal.reverses, original)
        self.assertEqual(reversal.document, sale)
        for field in (
            "quantity", "unit_cost", "company_id", "branch_id",
            "warehouse_id", "product_id",
        ):
            self.assertEqual(getattr(reversal, field), getattr(original, field), field)
        return reversal

    def test_cancel_preserves_historical_movement_and_traceability(self):
        sale = self.confirm_sale()
        original = self.original_movements(sale).get()

        CancelSale.execute(sale_id=sale.pk)

        sale.refresh_from_db()
        self.assertEqual(sale.status, DocumentStatus.CANCELLED)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("20"))
        self.assert_historical_reversal(sale, original)
        with self.assertRaises(ValueError):
            CancelSale.execute(sale_id=sale.pk)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("20"))
        self.assertEqual(original.reversal_movements.count(), 1)

    def test_cancel_uses_history_after_detail_quantity_and_price_change(self):
        sale = self.create_sale("10")
        ConfirmSale.execute(sale_id=sale.pk)
        original = self.original_movements(sale).get()
        self.assertEqual(original.quantity, Decimal("10"))
        self.assertEqual(original.unit_cost, Decimal("0"))
        sale.details.update(quantity=Decimal("6"), unit_price=Decimal("99"))

        CancelSale.execute(sale_id=sale.pk)

        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("20"))
        reversal = self.assert_historical_reversal(sale, original)
        self.assertEqual(reversal.quantity, Decimal("10"))
        self.assertEqual(reversal.unit_cost, Decimal("0"))

    def test_cancel_succeeds_after_details_are_deleted(self):
        sale = self.confirm_sale()
        original = self.original_movements(sale).get()
        sale.details.all().delete()

        CancelSale.execute(sale_id=sale.pk)

        sale.refresh_from_db()
        self.assertEqual(sale.status, DocumentStatus.CANCELLED)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("20"))
        self.assert_historical_reversal(sale, original)

    def test_confirmed_sale_without_history_is_rejected(self):
        sale = self.confirm_sale()
        # Simula pérdida del registro histórico, conservando la salida real de stock.
        self.original_movements(sale).delete()

        with self.assertRaises(InventoryException):
            CancelSale.execute(sale_id=sale.pk)

        sale.refresh_from_db()
        self.assertEqual(sale.status, DocumentStatus.CONFIRMED)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("15"))
        self.assertFalse(StockMovement.objects.exists())

    def create_sale_with_two_products(self):
        other = Product.objects.create(company=self.company, code="P002", name="Otro")
        Stock.objects.create(
            company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=other, quantity=Decimal("30"),
        )
        sale = CreateSale.execute(SaleCreateDTO(
            company_id=self.company.pk, branch_id=self.branch.pk,
            customer_id=self.customer.pk, warehouse_id=self.warehouse.pk,
            issue_date=date.today(), notes="Dos productos",
            details=[
                SaleDetailDTO(product_id=self.product.pk, quantity=Decimal("5"),
                              unit_price=Decimal("10"), discount=Decimal("0")),
                SaleDetailDTO(product_id=other.pk, quantity=Decimal("7"),
                              unit_price=Decimal("12"), discount=Decimal("0")),
            ],
        ))
        ConfirmSale.execute(sale_id=sale.pk)
        return sale, other

    def test_each_historical_movement_gets_its_own_compensation(self):
        sale, other = self.create_sale_with_two_products()
        originals = list(self.original_movements(sale))
        self.assertEqual(len(originals), 2)

        CancelSale.execute(sale_id=sale.pk)

        for original in originals:
            self.assert_historical_reversal(sale, original)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("20"))
        self.assertEqual(Stock.objects.get(product=other).quantity, Decimal("30"))
        self.assertEqual(StockMovement.objects.filter(reverses__isnull=False).count(), 2)

    def test_second_reversal_failure_rolls_back_entire_cancellation(self):
        sale, other = self.create_sale_with_two_products()
        originals = list(self.original_movements(sale))
        reverse = StockMovementReversalService.reverse
        seen = []

        def fail_on_second(*, movement, reversal_type, user=None):
            seen.append(movement.pk)
            if len(seen) == 2:
                self.assertTrue(originals[0].reversal_movements.exists())
                raise InventoryException("Fallo controlado en segunda reversión")
            return reverse(movement=movement, reversal_type=reversal_type, user=user)

        with patch.object(StockMovementReversalService, "reverse", side_effect=fail_on_second):
            with self.assertRaisesMessage(InventoryException, "Fallo controlado"):
                CancelSale.execute(sale_id=sale.pk)

        self.assertEqual(seen, [movement.pk for movement in originals])
        sale.refresh_from_db()
        self.assertEqual(sale.status, DocumentStatus.CONFIRMED)
        self.assertIsNone(sale.cancelled_at)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("15"))
        self.assertEqual(Stock.objects.get(product=other).quantity, Decimal("23"))
        self.assertFalse(StockMovement.objects.filter(reverses__isnull=False).exists())
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_cancel_selects_only_original_sale_movements_of_this_document(self):
        sale = self.confirm_sale()
        original = self.original_movements(sale).get()
        other_sale = self.confirm_sale()
        other_original = self.original_movements(other_sale).get()
        common = dict(company=self.company, branch=self.branch, warehouse=self.warehouse,
                      product=self.product, quantity=Decimal("1"))
        unrelated_type = StockMovement.objects.create(
            **common, movement_type=MovementType.ADJUSTMENT_OUT,
            content_type=ContentType.objects.get_for_model(sale), object_id=sale.pk,
        )
        unrelated_document = StockMovement.objects.create(
            **common, movement_type=MovementType.SALE,
            content_type=ContentType.objects.get_for_model(Warehouse), object_id=sale.pk,
        )
        compensatory_sale = StockMovement.objects.create(
            **common, movement_type=MovementType.SALE, reverses=unrelated_document,
            content_type=ContentType.objects.get_for_model(sale), object_id=sale.pk,
        )

        CancelSale.execute(sale_id=sale.pk)

        self.assert_historical_reversal(sale, original)
        for movement in (other_original, unrelated_type, compensatory_sale):
            self.assertFalse(movement.reversal_movements.exists())
        self.assertEqual(unrelated_document.reversal_movements.count(), 1)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("15"))
        self.assertEqual(StockMovement.objects.filter(movement_type=MovementType.RETURN_IN).count(), 1)
