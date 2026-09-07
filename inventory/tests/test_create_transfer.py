from datetime import date
from decimal import Decimal

from django.test import TestCase

from inventory.services.transfer.transfer_creator import TransferCreator
from core.constants.document_status import DocumentStatus
from core.models import Branch, Company

from catalog.models import Product

from people.models import Person

from inventory.dto import (
    TransferCreateDTO,
    TransferDetailDTO,
)
from inventory.models import (
    Transfer,
    TransferDetail,
    Warehouse,
)
from inventory.use_cases.create_transfer import (
    CreateTransfer,
)


class CreateTransferTest(TestCase):

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

        self.source = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="BOD001",
            name="Origen",
        )

        self.destination = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="BOD002",
            name="Destino",
        )

        self.product = Product.objects.create(
            company=self.company,
            code="P001",
            name="Producto Test",
        )

    def create_dto(self):

        return TransferCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            source_warehouse_id=self.source.id,
            destination_warehouse_id=self.destination.id,
            issue_date=date.today(),
            notes="Transferencia",
            details=[
                TransferDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("5"),
                )
            ],
        )

    def test_creator_persists_document_type(self):
        transfer = TransferCreator.create(self.create_dto())
        transfer.refresh_from_db()
        self.assertEqual(transfer.document_type.code, "INVENTORY_TRANSFER")

    def test_create_transfer(self):

        transfer = CreateTransfer.execute(
            self.create_dto()
        )

        self.assertEqual(
            transfer.status,
            DocumentStatus.DRAFT,
        )

        self.assertEqual(
            transfer.number,
            "",
        )

    def test_transfer_has_details(self):

        transfer = CreateTransfer.execute(
            self.create_dto()
        )

        self.assertEqual(
            transfer.details.count(),
            1,
        )

    def test_origin_destination_saved(self):

        transfer = CreateTransfer.execute(
            self.create_dto()
        )

        self.assertEqual(
            transfer.source_warehouse,
            self.source,
        )

        self.assertEqual(
            transfer.destination_warehouse,
            self.destination,
        )

    def test_detail_quantity(self):

        transfer = CreateTransfer.execute(
            self.create_dto()
        )

        detail = transfer.details.first()

        self.assertEqual(
            detail.quantity,
            Decimal("5"),
        )
