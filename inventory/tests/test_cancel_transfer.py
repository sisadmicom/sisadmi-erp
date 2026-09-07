from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.document_status import DocumentStatus
from core.models import Branch, Company, Sequence

from catalog.models import Product

from inventory.constants.movement_type import MovementType
from inventory.dto.transfer_create_dto import TransferCreateDTO
from inventory.dto.transfer_detail_dto import TransferDetailDTO
from inventory.models import (
    Stock,
    StockMovement,
    Transfer,
    Warehouse,
)
from inventory.use_cases.create_transfer import CreateTransfer
from inventory.use_cases.confirm_transfer import ConfirmTransfer
from inventory.use_cases.cancel_transfer import CancelTransfer

from people.models import Person



class CancelTransferTest(TestCase):

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
            is_active=True,
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

    def confirm_transfer(self, quantity="5"):

        transfer = self.create_transfer(quantity)

        ConfirmTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        transfer.refresh_from_db()

        return transfer

    def get_stock(self, warehouse):

        return Stock.objects.get(
            company=self.company,
            branch=self.branch,
            warehouse=warehouse,
            product=self.product,
        )

    def test_cancel_transfer_changes_status(self):

        transfer = self.confirm_transfer()

        self.assertEqual(
            transfer.status,
            DocumentStatus.CONFIRMED,
        )

        CancelTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        transfer.refresh_from_db()

        self.assertEqual(
            transfer.status,
            DocumentStatus.CANCELLED,
        )

    def test_cancel_transfer_restores_source_stock(self):

        transfer = self.confirm_transfer()

        CancelTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        stock = self.get_stock(
            self.source_warehouse
        )

        self.assertEqual(
            stock.quantity,
            Decimal("20"),
        )

    def test_cancel_transfer_restores_destination_stock(self):

        transfer = self.confirm_transfer()

        CancelTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        stock = self.get_stock(
            self.destination_warehouse
        )

        self.assertEqual(
            stock.quantity,
            Decimal("5"),
        )

    def test_cancel_transfer_creates_compensating_movements(self):

        transfer = self.confirm_transfer()

        CancelTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        movements = StockMovement.objects.filter(
            content_type__model="transfer",
            object_id=transfer.id,
        ).order_by("id")

        self.assertEqual(
            movements.count(),
            4,
        )

        self.assertEqual(
            movements.filter(
                movement_type=MovementType.TRANSFER_OUT
            ).count(),
            1,
        )

        self.assertEqual(
            movements.filter(
                movement_type=MovementType.TRANSFER_IN
            ).count(),
            1,
        )

        self.assertEqual(
            movements.filter(
                movement_type=MovementType.RETURN_IN
            ).count(),
            1,
        )

        self.assertEqual(
            movements.filter(
                movement_type=MovementType.RETURN_OUT
            ).count(),
            1,
        )

    def test_cancel_transfer_compensating_movements_use_correct_warehouses(
        self,
    ):

        transfer = self.confirm_transfer()

        CancelTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        movement_in = StockMovement.objects.get(
            content_type__model="transfer",
            object_id=transfer.id,
            movement_type=MovementType.RETURN_IN,
        )

        movement_out = StockMovement.objects.get(
            content_type__model="transfer",
            object_id=transfer.id,
            movement_type=MovementType.RETURN_OUT,
        )

        self.assertEqual(
            movement_in.warehouse,
            self.source_warehouse,
        )

        self.assertEqual(
            movement_out.warehouse,
            self.destination_warehouse,
        )

    def test_cancel_transfer_compensating_movements_have_correct_quantity(
        self,
    ):

        transfer = self.confirm_transfer("5")

        CancelTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        movement_in = StockMovement.objects.get(
            content_type__model="transfer",
            object_id=transfer.id,
            movement_type=MovementType.RETURN_IN,
        )

        movement_out = StockMovement.objects.get(
            content_type__model="transfer",
            object_id=transfer.id,
            movement_type=MovementType.RETURN_OUT,
        )

        self.assertEqual(
            movement_in.quantity,
            Decimal("5"),
        )

        self.assertEqual(
            movement_out.quantity,
            Decimal("5"),
        )

    def test_cancel_transfer_movements_use_transfer_number(self):

        transfer = self.confirm_transfer()

        CancelTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        movements = StockMovement.objects.filter(
            content_type__model="transfer",
            object_id=transfer.id,
        )

        for movement in movements:

            self.assertIn(
                transfer.number,
                movement.notes,
            )

    def test_cancel_transfer_associates_movements_to_document(self):

        transfer = self.confirm_transfer()

        CancelTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        movements = StockMovement.objects.filter(
            content_type__model="transfer",
            object_id=transfer.id,
        )

        self.assertEqual(
            movements.count(),
            4,
        )

        for movement in movements:

            self.assertEqual(
                movement.document,
                transfer,
            )

    def test_cancel_transfer_cannot_be_cancelled_twice(self):

        transfer = self.confirm_transfer()

        CancelTransfer.execute(
            transfer_id=transfer.id,
            user=None,
        )

        with self.assertRaises(ValueError):

            CancelTransfer.execute(
                transfer_id=transfer.id,
                user=None,
            )

        source_stock = self.get_stock(
            self.source_warehouse
        )

        destination_stock = self.get_stock(
            self.destination_warehouse
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
            4,
        )

    def test_cancel_transfer_without_destination_stock_fails_atomically(
        self,
    ):

        transfer = self.confirm_transfer()

        destination_stock = self.get_stock(
            self.destination_warehouse
        )

        destination_stock.quantity = Decimal("0")

        destination_stock.save(
            update_fields=[
                "quantity",
                "updated_at",
            ]
        )

        with self.assertRaises(Exception):

            CancelTransfer.execute(
                transfer_id=transfer.id,
                user=None,
            )

        transfer.refresh_from_db()

        source_stock = self.get_stock(
            self.source_warehouse
        )

        destination_stock = self.get_stock(
            self.destination_warehouse
        )

        self.assertEqual(
            transfer.status,
            DocumentStatus.CONFIRMED,
        )

        self.assertEqual(
            source_stock.quantity,
            Decimal("15"),
        )

        self.assertEqual(
            destination_stock.quantity,
            Decimal("0"),
        )

        self.assertEqual(
            StockMovement.objects.count(),
            2,
        )
