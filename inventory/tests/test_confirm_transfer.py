from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.document_status import DocumentStatus
from core.models import Branch, Company

from catalog.models import Product

from inventory.constants.movement_type import MovementType
from inventory.dto.transfer_create_dto import TransferCreateDTO
from inventory.dto.transfer_detail_dto import TransferDetailDTO
from inventory.models import Stock, StockMovement, Warehouse, Transfer
from inventory.use_cases.create_transfer import CreateTransfer
from inventory.use_cases.confirm_transfer import ConfirmTransfer

from people.models import Person

from core.models import Branch, Company, Sequence

class ConfirmTransferTest(TestCase):

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

        Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            document_type=DocumentType.objects.get(code=DocumentTypeCodes.INVENTORY_TRANSFER),
            name="Transferencias",
            prefix="TRF-",
            series="001",
            next_number=1,
            padding=6,
        )

        self.source_warehouse = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="BOD001",
            name="Bodega Origen",
            is_main=True,
        )

        self.destination_warehouse = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="BOD002",
            name="Bodega Destino",
        )

        self.product = Product.objects.create(
            company=self.company,
            code="P001",
            name="Producto Test",
        )

        Stock.objects.create(
            company=self.company,
            branch=self.branch,
            warehouse=self.source_warehouse,
            product=self.product,
            quantity=Decimal("20"),
            reserved_quantity=Decimal("0"),
        )

        Stock.objects.create(
            company=self.company,
            branch=self.branch,
            warehouse=self.destination_warehouse,
            product=self.product,
            quantity=Decimal("5"),
            reserved_quantity=Decimal("0"),
        )

    def create_transfer(self, quantity="5"):

        dto = TransferCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            source_warehouse_id=self.source_warehouse.id,
            destination_warehouse_id=self.destination_warehouse.id,
            issue_date=date.today(),
            notes="Transferencia de prueba",
            details=[
                TransferDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal(quantity),
                )
            ],
        )

        return CreateTransfer.execute(dto)

    def test_confirm_transfer_changes_status(self):

        transfer = self.create_transfer()

        self.assertEqual(
            transfer.status,
            DocumentStatus.DRAFT,
        )

        ConfirmTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        transfer.refresh_from_db()

        self.assertEqual(
            transfer.status,
            DocumentStatus.CONFIRMED,
        )

    def test_confirm_transfer_decreases_source_stock(self):

        transfer = self.create_transfer("5")

        ConfirmTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.source_warehouse,
            product=self.product,
        )

        self.assertEqual(
            stock.quantity,
            Decimal("15"),
        )

    def test_confirm_transfer_increases_destination_stock(self):

        transfer = self.create_transfer("5")

        ConfirmTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.destination_warehouse,
            product=self.product,
        )

        self.assertEqual(
            stock.quantity,
            Decimal("10"),
        )

    def test_confirm_transfer_creates_two_stock_movements(self):

        transfer = self.create_transfer("5")

        ConfirmTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        movements = StockMovement.objects.filter(
            content_type__model="transfer",
            object_id=transfer.id,
        ).order_by("id")

        self.assertEqual(
            movements.count(),
            2,
        )

        movement_out = movements.get(
            movement_type=MovementType.TRANSFER_OUT,
        )

        movement_in = movements.get(
            movement_type=MovementType.TRANSFER_IN,
        )

        self.assertEqual(
            movement_out.quantity,
            Decimal("5"),
        )

        self.assertEqual(
            movement_in.quantity,
            Decimal("5"),
        )

        self.assertEqual(
            movement_out.product,
            self.product,
        )

        self.assertEqual(
            movement_in.product,
            self.product,
        )

    def test_confirm_transfer_associates_movements_to_document(self):

        transfer = self.create_transfer("5")

        ConfirmTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        movements = StockMovement.objects.filter(
            content_type__model="transfer",
            object_id=transfer.id,
        )

        self.assertEqual(
            movements.count(),
            2,
        )

        for movement in movements:
            self.assertEqual(
                movement.document,
                transfer,
            )

        movement_out = movements.get(
            movement_type=MovementType.TRANSFER_OUT,
        )

        movement_in = movements.get(
            movement_type=MovementType.TRANSFER_IN,
        )

        self.assertEqual(
            movement_out.warehouse,
            self.source_warehouse,
        )

        self.assertEqual(
            movement_in.warehouse,
            self.destination_warehouse,
        )

    def test_confirm_transfer_without_stock_fails(self):

        transfer = self.create_transfer("25")

        with self.assertRaises(Exception):

            ConfirmTransfer.execute(
                transfer_id=transfer.id,
                user=None,
            )

        source_stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.source_warehouse,
            product=self.product,
        )

        destination_stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.destination_warehouse,
            product=self.product,
        )

        self.assertEqual(
            source_stock.quantity,
            Decimal("20"),
        )

        self.assertEqual(
            destination_stock.quantity,
            Decimal("5"),
        )

        self.assertEqual(
            StockMovement.objects.count(),
            0,
        )

    def test_confirm_transfer_cannot_be_confirmed_twice(self):

        transfer = self.create_transfer("5")

        ConfirmTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        with self.assertRaises(ValueError):

            ConfirmTransfer.execute(
                transfer_id=transfer.id,
                user=None,
            )

        source_stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.source_warehouse,
            product=self.product,
        )

        destination_stock = Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=self.destination_warehouse,
            product=self.product,
        )

        self.assertEqual(
            source_stock.quantity,
            Decimal("15"),
        )

        self.assertEqual(
            destination_stock.quantity,
            Decimal("10"),
        )

        self.assertEqual(
            StockMovement.objects.count(),
            2,
        )

    def test_confirm_transfer_generates_number(self):

        transfer = self.create_transfer("5")

        ConfirmTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        transfer.refresh_from_db()

        self.assertNotEqual(
            transfer.number,
            "",
        )

        self.assertTrue(
            transfer.number.startswith("TRF-"),
        )

    def test_confirm_transfer_movements_use_transfer_number(self):

        transfer = self.create_transfer("5")

        ConfirmTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        transfer.refresh_from_db()

        movements = StockMovement.objects.filter(
            content_type__model="transfer",
            object_id=transfer.id,
        )

        movement_out = movements.get(
            movement_type=MovementType.TRANSFER_OUT,
        )

        movement_in = movements.get(
            movement_type=MovementType.TRANSFER_IN,
        )

        self.assertEqual(
            movement_out.notes,
            f"Transferencia salida {transfer.number}",
        )

        self.assertEqual(
            movement_in.notes,
            f"Transferencia entrada {transfer.number}",
        )