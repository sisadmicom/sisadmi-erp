from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.document_status import DocumentStatus
from core.models import Branch, Company, Sequence

from catalog.models import Product

from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.kardex.kardex_service import KardexService

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
            f"Anulación venta {sale.number}",
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

        with self.assertRaises(ValueError):

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
