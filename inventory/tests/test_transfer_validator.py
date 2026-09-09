from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.constants.document_status import DocumentStatus
from core.exceptions import EmptyDocument, InvalidQuantity
from core.models import Branch, Company, DocumentType

from catalog.models import Product

from people.models import Person

from inventory.dto import (
    TransferCreateDTO,
    TransferDetailDTO,
)
from inventory.models import Warehouse, Transfer, TransferDetail
from inventory.validators import TransferValidator


class TransferValidatorTest(TestCase):

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
            name="Bodega Origen",
        )

        self.destination = Warehouse.objects.create(
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

    def make_dto(
        self,
        source=None,
        destination=None,
        details=None,
    ):

        return TransferCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            source_warehouse_id=(
                source or self.source.id
            ),
            destination_warehouse_id=(
                destination or self.destination.id
            ),
            issue_date=date.today(),
            notes="Transferencia de prueba",
            details=(
                details
                if details is not None
                else [
                    TransferDetailDTO(
                        product_id=self.product.id,
                        quantity=Decimal("5"),
                    )
                ]
            ),
        )

    def test_valid_transfer(self):

        dto = self.make_dto()

        TransferValidator.validate(dto)

    def test_transfer_without_details_fails(self):

        dto = self.make_dto(
            details=[]
        )

        with self.assertRaises(EmptyDocument):
            TransferValidator.validate(dto)

    def test_same_warehouse_fails(self):

        dto = self.make_dto(
            destination=self.source.id
        )

        with self.assertRaisesMessage(ValueError, "La bodega origen y destino no pueden ser la misma."):
            TransferValidator.validate(dto)

    def test_zero_quantity_fails(self):

        dto = self.make_dto(
            details=[
                TransferDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("0"),
                )
            ]
        )

        with self.assertRaises(InvalidQuantity):
            TransferValidator.validate(dto)

    def test_negative_quantity_fails(self):

        dto = self.make_dto(
            details=[
                TransferDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("-1"),
                )
            ]
        )

        with self.assertRaises(InvalidQuantity):
            TransferValidator.validate(dto)

    def test_duplicate_product_fails(self):

        dto = self.make_dto(
            details=[
                TransferDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("5"),
                ),
                TransferDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("3"),
                ),
            ]
        )

        with self.assertRaisesMessage(ValueError, "No se puede repetir un producto en una transferencia."):
            TransferValidator.validate(dto)

    def test_source_warehouse_wrong_company_fails(self):

        other_person = Person.objects.create(
            identification="1790000001002",
            person_type="LEGAL",
            full_name="Otra Empresa",
        )

        other_company = Company.objects.create(
            person=other_person,
            commercial_name="Otra Empresa",
        )

        other_branch = Branch.objects.create(
            company=other_company,
            code="001",
            name="Matriz",
        )

        other_warehouse = Warehouse.objects.create(
            company=other_company,
            branch=other_branch,
            code="BOD001",
            name="Otra Bodega",
        )

        for side, label in (("source", "origen"), ("destination", "destino")):
            with self.subTest(side=side):
                dto = self.make_dto(**{side: other_warehouse.id})
                with self.assertRaisesMessage(ValueError, f"La bodega {label} no pertenece a la empresa."):
                    TransferValidator.validate(dto)


    def test_warehouses_wrong_branch_fail(self):
        other_branch = Branch.objects.create(company=self.company, code="002", name="Sucursal")
        other_warehouse = Warehouse.objects.create(
            company=self.company, branch=other_branch, code="OTHER", name="Otra bodega",
        )
        for side, label in (("source", "origen"), ("destination", "destino")):
            with self.subTest(side=side):
                dto = self.make_dto(**{side: other_warehouse.pk})
                with self.assertRaisesMessage(ValueError, f"La bodega {label} no pertenece a la sucursal."):
                    TransferValidator.validate(dto)

    def make_transfer(self, quantity="5", status=DocumentStatus.DRAFT):
        transfer = Transfer.objects.create(
            company=self.company, branch=self.branch,
            document_type=DocumentType.objects.get(code=Transfer.DOCUMENT_TYPE_CODE),
            source_warehouse=self.source, destination_warehouse=self.destination,
            status=status,
        )
        if quantity is not None:
            TransferDetail.objects.create(
                transfer=transfer, product=self.product, line=1, quantity=Decimal(quantity),
            )
        return transfer

    def test_valid_confirmation(self):
        TransferValidator.validate_confirmation(self.make_transfer())

    def test_confirmation_without_details_raises_empty_document(self):
        with self.assertRaises(EmptyDocument):
            TransferValidator.validate_confirmation(self.make_transfer(quantity=None))

    def test_confirmation_nonpositive_quantity_raises_invalid_quantity(self):
        for quantity in ("0", "-1"):
            with self.subTest(quantity=quantity), self.assertRaises(InvalidQuantity):
                TransferValidator.validate_confirmation(self.make_transfer(quantity=quantity))

    def test_confirmation_requires_draft(self):
        for status in (DocumentStatus.CONFIRMED, DocumentStatus.CANCELLED):
            with self.subTest(status=status), self.assertRaisesMessage(ValueError, "La transferencia no está en borrador."):
                TransferValidator.validate_confirmation(self.make_transfer(status=status))

    def test_confirmation_rejects_same_warehouse(self):
        transfer = self.make_transfer()
        transfer.destination_warehouse = self.source
        with self.assertRaisesMessage(ValueError, "La bodega origen y destino no pueden ser la misma."):
            TransferValidator.validate_confirmation(transfer)

    def test_confirmation_rejects_duplicate_product(self):
        transfer = self.make_transfer()
        TransferDetail.objects.create(transfer=transfer, product=self.product, line=2, quantity=Decimal("1"))
        with self.assertRaisesMessage(ValueError, "No se puede repetir un producto en una transferencia."):
            TransferValidator.validate_confirmation(transfer)

    def test_cancellation_requires_confirmed_and_rejects_cancelled(self):
        for status, message in (
            (DocumentStatus.DRAFT, "Solo se pueden anular transferencias confirmadas."),
            (DocumentStatus.CANCELLED, "La transferencia ya fue anulada."),
        ):
            with self.subTest(status=status), self.assertRaisesMessage(ValueError, message):
                TransferValidator.validate_cancellation(self.make_transfer(status=status))

    def test_cancellation_without_details_keeps_value_error(self):
        transfer = self.make_transfer(quantity=None, status=DocumentStatus.CONFIRMED)
        with self.assertRaisesMessage(ValueError, "La transferencia no tiene detalles."):
            TransferValidator.validate_cancellation(transfer)

    def test_cancellation_keeps_existing_quantity_behavior(self):
        for quantity in ("5", "0", "-1"):
            with self.subTest(quantity=quantity):
                TransferValidator.validate_cancellation(self.make_transfer(quantity=quantity, status=DocumentStatus.CONFIRMED))
