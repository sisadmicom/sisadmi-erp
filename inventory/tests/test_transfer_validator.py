from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Branch, Company

from catalog.models import Product

from people.models import Person

from inventory.dto import (
    TransferCreateDTO,
    TransferDetailDTO,
)
from inventory.models import Warehouse
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

        with self.assertRaises(ValueError):
            TransferValidator.validate(dto)

    def test_same_warehouse_fails(self):

        dto = self.make_dto(
            destination=self.source.id
        )

        with self.assertRaises(ValueError):
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

        with self.assertRaises(ValueError):
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

        with self.assertRaises(ValueError):
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

        with self.assertRaises(ValueError):
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

        dto = self.make_dto(
            source=other_warehouse.id
        )

        with self.assertRaises(ValueError):
            TransferValidator.validate(dto)
