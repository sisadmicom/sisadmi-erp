from datetime import date
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

from django.test import TestCase

from django.core.exceptions import ValidationError

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.document_status import DocumentStatus
from core.models import Branch, Company, Sequence
from core.exceptions.inventory import InventoryException

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
from inventory.services.stock.decrease_stock import DecreaseStock

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
            if movement.reverses_id is None:
                self.assertIn(transfer.number, movement.notes)
            else:
                self.assertIn("Reversión", movement.notes)

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

        with self.assertRaisesMessage(
            ValueError,
            "El documento ya fue anulado.",
        ):
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

    def test_cancel_draft_transfer_uses_universal_lifecycle_error(self):

        transfer = self.create_transfer()

        with self.assertRaisesMessage(
            ValueError,
            "Solo se pueden anular documentos confirmados.",
        ):
            CancelTransfer.execute(
                transfer_id=transfer.id,
                user=None,
            )

        transfer.refresh_from_db()
        self.assertEqual(transfer.status, DocumentStatus.DRAFT)

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

    def historical_movements(self, transfer):
        return StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(transfer),
            object_id=transfer.pk,
            reverses__isnull=True,
        ).order_by("id")

    def test_cancel_transfer_reverses_historical_movements_with_traceability(self):
        transfer = self.confirm_transfer()
        originals = list(self.historical_movements(transfer))
        CancelTransfer.execute(transfer_id=transfer.id, user=None)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, DocumentStatus.CANCELLED)
        self.assertEqual(self.get_stock(self.source_warehouse).quantity, Decimal("20"))
        self.assertEqual(self.get_stock(self.destination_warehouse).quantity, Decimal("5"))
        for original in originals:
            reversal = original.reversal_movements.get()
            expected_type = (MovementType.RETURN_OUT if original.movement_type == MovementType.TRANSFER_IN else MovementType.RETURN_IN)
            self.assertEqual(reversal.movement_type, expected_type)
            self.assertEqual(reversal.reverses, original)
            for field in ("company_id", "branch_id", "warehouse_id", "product_id", "quantity", "unit_cost"):
                self.assertEqual(getattr(reversal, field), getattr(original, field), field)
            self.assertEqual(reversal.document, transfer)
            self.assertEqual(original.reversal_movements.count(), 1)

    def test_cancel_transfer_reverses_two_products_with_traceability(self):
        other = Product.objects.create(
            company=self.company, code="P002", name="Otro producto",
        )
        Stock.objects.create(
            company=self.company,
            branch=self.branch,
            warehouse=self.source_warehouse,
            product=other,
            quantity=Decimal("20"),
        )
        transfer = CreateTransfer.execute(TransferCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            source_warehouse_id=self.source_warehouse.id,
            destination_warehouse_id=self.destination_warehouse.id,
            issue_date=date.today(),
            notes="Dos productos",
            details=[
                TransferDetailDTO(product_id=self.product.id, quantity=Decimal("5")),
                TransferDetailDTO(product_id=other.id, quantity=Decimal("7")),
            ],
        ))
        ConfirmTransfer.execute(transfer_id=transfer.id, user=None)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, DocumentStatus.CONFIRMED)
        originals = list(self.historical_movements(transfer))
        self.assertEqual(len(originals), 4)
        self.assertCountEqual(
            [(movement.product_id, movement.movement_type) for movement in originals],
            [
                (product.pk, movement_type)
                for product in (self.product, other)
                for movement_type in (MovementType.TRANSFER_OUT, MovementType.TRANSFER_IN)
            ],
        )

        CancelTransfer.execute(transfer_id=transfer.id, user=None)

        transfer.refresh_from_db()
        self.assertEqual(transfer.status, DocumentStatus.CANCELLED)
        expected_types = {
            MovementType.TRANSFER_IN: MovementType.RETURN_OUT,
            MovementType.TRANSFER_OUT: MovementType.RETURN_IN,
        }
        for original in originals:
            with self.subTest(original=original.pk, product=original.product_id):
                self.assertEqual(original.reversal_movements.count(), 1)
                reversal = original.reversal_movements.get()
                self.assertEqual(reversal.reverses, original)
                self.assertEqual(reversal.movement_type, expected_types[original.movement_type])
                for field in ("quantity", "product", "warehouse", "company", "branch", "document"):
                    self.assertEqual(getattr(reversal, field), getattr(original, field), field)

    def test_cancel_transfer_uses_historical_quantity_after_detail_mutation(self):
        transfer = self.confirm_transfer("10")
        originals = list(self.historical_movements(transfer))
        transfer.details.update(quantity=Decimal("3"))
        CancelTransfer.execute(transfer_id=transfer.id, user=None)
        for original in originals:
            self.assertEqual(original.reversal_movements.get().quantity, Decimal("10"))

    def test_cancel_transfer_works_after_details_deleted(self):
        transfer = self.confirm_transfer()
        originals = list(self.historical_movements(transfer))
        transfer.details.all().delete()
        CancelTransfer.execute(transfer_id=transfer.id, user=None)
        self.assertEqual(len(originals), 2)
        self.assertEqual(StockMovement.objects.filter(reverses__isnull=False).count(), 2)

    def test_cancel_transfer_uses_historical_warehouses_after_header_mutation(self):
        transfer = self.confirm_transfer()
        originals = list(self.historical_movements(transfer))
        other_source = Warehouse.objects.create(company=self.company, branch=self.branch, code="B003", name="Otra Origen")
        other_destination = Warehouse.objects.create(company=self.company, branch=self.branch, code="B004", name="Otra Destino")
        transfer.source_warehouse = other_source
        transfer.destination_warehouse = other_destination
        transfer.save(update_fields=["source_warehouse", "destination_warehouse"])
        CancelTransfer.execute(transfer_id=transfer.id, user=None)
        for original in originals:
            self.assertEqual(original.reversal_movements.get().warehouse_id, original.warehouse_id)
        self.assertEqual(self.get_stock(self.source_warehouse).quantity, Decimal("20"))
        self.assertEqual(self.get_stock(self.destination_warehouse).quantity, Decimal("5"))

    def test_confirmed_transfer_without_history_is_rejected(self):
        transfer = self.confirm_transfer()
        self.historical_movements(transfer).delete()
        with self.assertRaises(InventoryException):
            CancelTransfer.execute(transfer_id=transfer.id, user=None)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, DocumentStatus.CONFIRMED)
        self.assertEqual(self.get_stock(self.source_warehouse).quantity, Decimal("15"))
        self.assertEqual(self.get_stock(self.destination_warehouse).quantity, Decimal("10"))
        self.assertFalse(StockMovement.objects.exists())

    def test_incomplete_transfer_history_is_rejected(self):
        transfer = self.confirm_transfer()
        self.historical_movements(transfer).filter(movement_type=MovementType.TRANSFER_IN).delete()
        with self.assertRaises(InventoryException):
            CancelTransfer.execute(transfer_id=transfer.id, user=None)
        self.assertEqual(StockMovement.objects.count(), 1)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, DocumentStatus.CONFIRMED)

    def test_unbalanced_transfer_history_is_rejected(self):
        transfer = self.confirm_transfer()
        StockMovement.objects.create(company=self.company, branch=self.branch, warehouse=self.destination_warehouse, product=self.product, movement_type=MovementType.TRANSFER_IN, quantity=Decimal("1"), content_type=ContentType.objects.get_for_model(transfer), object_id=transfer.pk)
        with self.assertRaises(InventoryException):
            CancelTransfer.execute(transfer_id=transfer.id, user=None)
        self.assertEqual(StockMovement.objects.filter(reverses__isnull=False).count(), 0)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, DocumentStatus.CONFIRMED)

    def test_cancel_transfer_rolls_back_when_second_destination_reversal_lacks_stock(self):
        other = Product.objects.create(company=self.company, code="P002", name="Otro")
        Stock.objects.create(company=self.company, branch=self.branch, warehouse=self.destination_warehouse, product=other, quantity=30)
        Stock.objects.create(company=self.company, branch=self.branch, warehouse=self.source_warehouse, product=other, quantity=20)
        transfer = CreateTransfer.execute(TransferCreateDTO(company_id=self.company.id, branch_id=self.branch.id, source_warehouse_id=self.source_warehouse.id, destination_warehouse_id=self.destination_warehouse.id, issue_date=date.today(), notes="Dos", details=[TransferDetailDTO(product_id=self.product.id, quantity=Decimal("5")), TransferDetailDTO(product_id=other.id, quantity=Decimal("7"))]))
        ConfirmTransfer.execute(transfer_id=transfer.id, user=None)
        DecreaseStock().execute(company=self.company, branch=self.branch, warehouse=self.destination_warehouse, product=other, quantity=Decimal("31"), movement_type=MovementType.ADJUSTMENT_OUT)
        originals = list(self.historical_movements(transfer))
        with self.assertRaises(ValidationError):
            CancelTransfer.execute(transfer_id=transfer.id, user=None)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, DocumentStatus.CONFIRMED)
        self.assertIsNone(transfer.cancelled_at)
        self.assertEqual(self.get_stock(self.source_warehouse).quantity, Decimal("15"))
        self.assertEqual(Stock.objects.get(company=self.company, branch=self.branch, warehouse=self.source_warehouse, product=other).quantity, Decimal("13"))
        self.assertEqual(self.get_stock(self.destination_warehouse).quantity, Decimal("10"))
        self.assertEqual(Stock.objects.get(company=self.company, branch=self.branch, warehouse=self.destination_warehouse, product=other).quantity, Decimal("6"))
        self.assertFalse(StockMovement.objects.filter(reverses__isnull=False).exists())
        for original in originals:
            self.assertFalse(original.reversal_movements.exists())

    def test_cancel_transfer_selects_only_original_movements(self):
        transfer = self.confirm_transfer()
        originals = list(self.historical_movements(transfer))
        self.assertCountEqual(
            [movement.movement_type for movement in originals],
            [MovementType.TRANSFER_IN, MovementType.TRANSFER_OUT],
        )
        other_transfer = self.confirm_transfer()
        other_movements = list(self.historical_movements(other_transfer))
        movement_data = {
            "company": self.company,
            "branch": self.branch,
            "warehouse": self.source_warehouse,
            "product": self.product,
            "quantity": Decimal("1"),
            "content_type": ContentType.objects.get_for_model(transfer),
            "object_id": transfer.pk,
        }
        unrelated = StockMovement.objects.create(
            **movement_data, movement_type=MovementType.ADJUSTMENT_IN,
        )
        adjustment = StockMovement.objects.create(
            **movement_data, movement_type=MovementType.ADJUSTMENT_OUT,
        )
        # Match the transfer type/document filters, but reverse an independent
        # adjustment so both legitimate transfer originals remain reversible.
        compensatory = StockMovement.objects.create(
            **movement_data,
            movement_type=MovementType.TRANSFER_IN,
            reverses=adjustment,
        )
        ignored_ids = [
            movement.pk
            for movement in [*other_movements, unrelated, adjustment, compensatory]
        ]
        ignored_before = list(
            StockMovement.objects.filter(pk__in=ignored_ids).order_by("pk").values()
        )
        movement_ids_before = set(StockMovement.objects.values_list("pk", flat=True))

        CancelTransfer.execute(transfer_id=transfer.id, user=None)

        transfer.refresh_from_db()
        self.assertEqual(transfer.status, DocumentStatus.CANCELLED)
        expected_types = {
            MovementType.TRANSFER_IN: MovementType.RETURN_OUT,
            MovementType.TRANSFER_OUT: MovementType.RETURN_IN,
        }
        reversal_ids = set()
        for original in originals:
            with self.subTest(original=original.pk):
                self.assertEqual(original.reversal_movements.count(), 1)
                reversal = original.reversal_movements.get()
                reversal_ids.add(reversal.pk)
                self.assertEqual(reversal.reverses, original)
                self.assertEqual(reversal.movement_type, expected_types[original.movement_type])
                for field in ("quantity", "product", "warehouse", "company", "branch", "document"):
                    self.assertEqual(getattr(reversal, field), getattr(original, field), field)
        self.assertEqual(
            list(StockMovement.objects.filter(pk__in=ignored_ids).order_by("pk").values()),
            ignored_before,
        )
        self.assertEqual(
            set(StockMovement.objects.filter(reverses_id__in=ignored_ids).values_list("pk", flat=True)),
            {compensatory.pk},
        )
        self.assertEqual(
            set(StockMovement.objects.values_list("pk", flat=True)),
            movement_ids_before | reversal_ids,
        )
        for movement in [*other_movements, unrelated, compensatory]:
            with self.subTest(ignored_movement=movement.pk):
                self.assertFalse(movement.reversal_movements.exists())
        self.assertEqual(adjustment.reversal_movements.get(), compensatory)
        other_transfer.refresh_from_db()
        self.assertEqual(other_transfer.status, DocumentStatus.CONFIRMED)
