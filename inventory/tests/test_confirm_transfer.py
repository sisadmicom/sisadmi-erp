from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

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
from inventory.services.transfer.transfer_confirmation_service import TransferConfirmationService
from inventory.services.stock.decrease_stock import DecreaseStock
from inventory.services.stock.increase_stock import IncreaseStock
from core.exceptions.inventory import InventoryException

from people.models import Person

from core.models import Branch, Company, Sequence

def transfer_lifecycle_snapshot(transfer, sequence):
    """Estado persistido completo relevante para repetición y rollback."""
    return {
        **Transfer.objects.values(
            "status", "number", "confirmed_at", "confirmed_by_id",
            "cancelled_at", "cancelled_by_id",
        ).get(pk=transfer.pk),
        "next_number": Sequence.objects.get(pk=sequence.pk).next_number,
        "stocks": list(Stock.objects.filter(
            company_id=transfer.company_id, branch_id=transfer.branch_id,
        ).order_by("pk").values(
            "warehouse_id", "product_id", "quantity", "reserved_quantity",
        )),
        "movements": list(StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(Transfer),
            object_id=transfer.pk,
        ).order_by("pk").values(
            "id", "movement_type", "quantity", "unit_cost", "reverses_id",
            "company_id", "branch_id", "warehouse_id", "product_id", "created_by_id",
        )),
    }


class TransferFixture:
    """Dataset de confirmación existente compartido con TransactionTestCase."""

    def setUp(self):
        super().setUp()
        document_type, _ = DocumentType.objects.get_or_create(
            code=DocumentTypeCodes.INVENTORY_TRANSFER,
            defaults={
                "name": "Transferencia de inventario", "category": "INVENTORY",
                "requires_detail": True, "affects_inventory": True,
                "inventory_behavior": "TRANSFER", "line_behavior": "QUANTITY",
                "can_issue_electronic": False,
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

        self.sequence = Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            document_type=document_type,
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

class ConfirmTransferTest(TransferFixture, TestCase):
    maxDiff = None

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

        with self.assertRaisesMessage(ValueError, "Solo se pueden confirmar documentos en borrador."):

            ConfirmTransfer.execute(
                transfer_id=transfer.id,
                user=None,
            )
        transfer.status = DocumentStatus.CANCELLED
        transfer.save(update_fields=["status"])
        with self.assertRaisesMessage(ValueError, "Solo se pueden confirmar documentos en borrador."):
            ConfirmTransfer.execute(transfer_id=transfer.id, user=None)


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


    def test_stale_transfer_cannot_repeat_confirmation(self):
        first_user = get_user_model().objects.create_user(username="transfer-first")
        other_user = get_user_model().objects.create_user(username="transfer-stale")
        transfer = self.create_transfer()
        stale = Transfer.objects.get(pk=transfer.pk)
        self.assertEqual(stale.status, DocumentStatus.DRAFT)
        ConfirmTransfer.execute(transfer_id=transfer.pk, user=first_user)
        before = transfer_lifecycle_snapshot(transfer, self.sequence)

        try:
            TransferConfirmationService.confirm(transfer_id=stale.pk, user=other_user)
        except (ValueError, InventoryException) as error:
            outcome = (type(error).__name__, str(error))
        else:
            outcome = ("success", "")
        self.assertEqual(
            {"outcome": outcome, **transfer_lifecycle_snapshot(transfer, self.sequence)},
            {"outcome": ("ValueError", "Solo se pueden confirmar documentos en borrador."), **before},
        )

    def test_confirmation_effect_failure_rolls_back_entire_operation(self):
        user = get_user_model().objects.create_user(username="transfer-rollback")
        for stock_service, expected_types, expected_quantities in (
            (DecreaseStock, [MovementType.TRANSFER_OUT], [Decimal("15"), Decimal("5")]),
            (IncreaseStock, [MovementType.TRANSFER_OUT, MovementType.TRANSFER_IN], [Decimal("15"), Decimal("10")]),
        ):
            with self.subTest(after_effect=expected_types[-1]):
                transfer = self.create_transfer()
                before = transfer_lifecycle_snapshot(transfer, self.sequence)
                observed = []
                execute = stock_service.execute

                def effect_then_fail(service, **kwargs):
                    # El efecto SQL real se completa antes del fallo inyectado.
                    execute(service, **kwargs)
                    observed.append(transfer_lifecycle_snapshot(transfer, self.sequence))
                    raise RuntimeError("Fallo posterior al efecto de transferencia.")

                with patch.object(stock_service, "execute", new=effect_then_fail):
                    with self.assertRaisesMessage(RuntimeError, "Fallo posterior al efecto de transferencia."):
                        ConfirmTransfer.execute(transfer_id=transfer.pk, user=user)
                self.assertEqual(len(observed), 1)
                checkpoint = observed[0]
                self.assertEqual(checkpoint["status"], DocumentStatus.CONFIRMED)
                self.assertTrue(checkpoint["number"])
                self.assertIsNotNone(checkpoint["confirmed_at"])
                self.assertEqual(checkpoint["confirmed_by_id"], user.pk)
                self.assertEqual(checkpoint["next_number"], before["next_number"] + 1)
                self.assertEqual([row["movement_type"] for row in checkpoint["movements"]], expected_types)
                self.assertEqual([row["quantity"] for row in checkpoint["stocks"]], expected_quantities)
                self.assertEqual(transfer_lifecycle_snapshot(transfer, self.sequence), before)
