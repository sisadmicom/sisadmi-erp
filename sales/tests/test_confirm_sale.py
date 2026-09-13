from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.document_status import DocumentStatus
from core.constants.movement_types import MovementTypes
from core.models import Branch, Company, Sequence

from catalog.models import Product

from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.kardex import KardexService
from inventory.constants.movement_type import MovementType

from people.models import Customer, Person

from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.models import Sale
from sales.services.sale_confirmation_service import SaleConfirmationService
from sales.use_cases.create_sale import CreateSale
from sales.use_cases.confirm_sale import ConfirmSale


class SaleFixture:
    """Dataset existente de Sales, compartido con TransactionTestCase."""

    def setUp(self):
        super().setUp()

        # TransactionTestCase vacía los catálogos entre pruebas.
        document_type, _ = DocumentType.objects.get_or_create(
            code=DocumentTypeCodes.SALES_INVOICE,
            defaults={
                "name": "Factura de venta",
                "category": "SALES",
                "line_behavior": "COMMERCIAL",
                "requires_detail": True,
                "affects_inventory": True,
                "inventory_behavior": "OUT",
                "can_issue_electronic": True,
            },
        )

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

        self.sequence = Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            document_type=document_type,
            name="Ventas",
            prefix="VEN-",
            series="001",
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

    def create_sale(self, quantity):

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


class ConfirmSaleTest(SaleFixture, TestCase):
    maxDiff = None

    def test_confirm_sale_changes_status(self):

        sale = self.create_sale("5")

        self.assertEqual(
            sale.status,
            DocumentStatus.DRAFT,
        )

        ConfirmSale.execute(
            sale_id=sale.id,
            user=None,
        )

        sale.refresh_from_db()

        self.assertNotEqual(
            sale.status,
            DocumentStatus.DRAFT,
        )

    def test_confirm_sale_decreases_stock(self):

        sale = self.create_sale("5")

        ConfirmSale.execute(
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
            Decimal("15"),
        )

    def test_confirm_sale_creates_stock_movement(self):

        sale = self.create_sale("5")

        ConfirmSale.execute(
            sale_id=sale.id,
            user=None,
        )

        movement = StockMovement.objects.get(
            content_type__model="sale",
            object_id=sale.id,
        )

        """movement = StockMovement.objects.get(
            document=sale,
        )"""

        self.assertEqual(
            movement.movement_type,
            MovementTypes.SALE,
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

    def test_confirm_sale_updates_kardex(self):

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

        sale = self.create_sale("5")

        ConfirmSale.execute(
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
            2,
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

    def test_confirm_sale_without_stock_fails(self):

        sale = self.create_sale("25")
        user = get_user_model().objects.create_user(username="confirmation-rollback")
        before = {
            "status": sale.status,
            "number": sale.number,
            "confirmed_at": sale.confirmed_at,
            "confirmed_by_id": sale.confirmed_by_id,
            "next_number": self.sequence.next_number,
        }

        with self.assertRaises(ValidationError):
            ConfirmSale.execute(
                sale_id=sale.id,
                user=user,
            )

        sale.refresh_from_db()
        self.sequence.refresh_from_db()
        self.assertEqual(
            {
                "status": sale.status,
                "number": sale.number,
                "confirmed_at": sale.confirmed_at,
                "confirmed_by_id": sale.confirmed_by_id,
                "next_number": self.sequence.next_number,
            },
            before,
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
            0,
        )

    def test_confirm_sale_cannot_be_confirmed_twice(self):

        sale = self.create_sale("5")

        ConfirmSale.execute(
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
            Decimal("15"),
        )

        with self.assertRaisesMessage(ValueError, "Solo se pueden confirmar documentos en borrador."):
            ConfirmSale.execute(
                sale_id=sale.id,
                user=None,
            )
        sale.status = DocumentStatus.CANCELLED
        sale.save(update_fields=["status"])
        with self.assertRaisesMessage(ValueError, "Solo se pueden confirmar documentos en borrador."):
            ConfirmSale.execute(sale_id=sale.id, user=None)


        stock.refresh_from_db()

        self.assertEqual(
            stock.quantity,
            Decimal("15"),
        )

        self.assertEqual(
            StockMovement.objects.count(),
            1,
        )

    def test_stale_sale_cannot_repeat_confirmation(self):
        sale = self.create_sale("5")
        stale = Sale.objects.get(pk=sale.pk)
        self.assertEqual(stale.status, DocumentStatus.DRAFT)
        ConfirmSale.execute(sale_id=sale.pk, user=None)
        sale.refresh_from_db()
        self.sequence.refresh_from_db()
        confirmed_number = sale.number
        confirmed_at = sale.confirmed_at
        next_number = self.sequence.next_number

        # El llamador conserva DRAFT, pero solo su identidad cruza la frontera.
        # El servicio debe decidir usando la Sale persistida y bloqueada.
        try:
            SaleConfirmationService.confirm(sale_id=stale.pk, user=None)
        except ValueError as error:
            outcome = (type(error).__name__, str(error))
        else:
            outcome = ("success", "")

        sale.refresh_from_db()
        self.sequence.refresh_from_db()
        stock = Stock.objects.get(warehouse=self.warehouse, product=self.product)
        movements = StockMovement.objects.filter(
            content_type__model="sale", object_id=sale.pk,
            movement_type=MovementType.SALE,
        )
        self.assertEqual(
            {
                "outcome": outcome,
                "status": sale.status,
                "number": sale.number,
                "confirmed_at": sale.confirmed_at,
                "next_number": self.sequence.next_number,
                "stock": stock.quantity,
                "sale_quantities": list(movements.order_by("id").values_list("quantity", flat=True)),
                "movement_count": StockMovement.objects.count(),
            },
            {
                "outcome": ("ValueError", "Solo se pueden confirmar documentos en borrador."),
                "status": DocumentStatus.CONFIRMED,
                "number": confirmed_number,
                "confirmed_at": confirmed_at,
                "next_number": next_number,
                "stock": Decimal("15"),
                "sale_quantities": [Decimal("5")],
                "movement_count": 1,
            },
        )
