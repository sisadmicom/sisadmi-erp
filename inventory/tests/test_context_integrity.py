from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Product
from core.constants.document_type_codes import DocumentTypeCodes
from core.models import Branch, Company, DocumentType
from inventory.constants.movement_type import MovementType
from inventory.dto.transfer_create_dto import TransferCreateDTO
from inventory.dto.transfer_detail_dto import TransferDetailDTO
from inventory.models import Stock, StockMovement, Transfer, TransferDetail, Warehouse
from inventory.services.movement.create_stock_movement import CreateStockMovement
from inventory.services.stock.increase_stock import IncreaseStock
from inventory.use_cases.create_transfer import CreateTransfer
from people.models import Customer, Person, Supplier
from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.use_cases.create_purchase import CreatePurchase
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.use_cases.create_sale import CreateSale


class ContextIntegrityTests(TestCase):
    def setUp(self):
        self.type_sale = DocumentType.objects.get(code=DocumentTypeCodes.SALES_INVOICE)
        self.type_purchase = DocumentType.objects.get(code=DocumentTypeCodes.PURCHASE_INVOICE)
        self.type_transfer = DocumentType.objects.get(code=DocumentTypeCodes.INVENTORY_TRANSFER)

        self.company = self._company("A")
        self.other_company = self._company("B")
        self.branch = Branch.objects.create(company=self.company, code="A01", name="A")
        self.other_branch_same_company = Branch.objects.create(
            company=self.company, code="A02", name="A2",
        )
        self.other_branch = Branch.objects.create(company=self.other_company, code="B01", name="B")
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, code="WA", name="A", is_main=True,
        )
        self.other_warehouse = Warehouse.objects.create(
            company=self.other_company, branch=self.other_branch, code="WB", name="B", is_main=True,
        )
        self.other_branch_warehouse = Warehouse.objects.create(
            company=self.company, branch=self.other_branch_same_company,
            code="WA2", name="A2", is_main=True,
        )
        self.product = Product.objects.create(company=self.company, code="PA", name="A")
        self.other_product = Product.objects.create(company=self.other_company, code="PB", name="B")
        self.customer = Customer.objects.create(
            person=Person.objects.create(identification="0999999999001", person_type="LEGAL", full_name="Cliente"),
        )
        self.supplier = Supplier.objects.create(
            person=Person.objects.create(identification="0999999999002", person_type="LEGAL", full_name="Proveedor"),
        )

    def _company(self, suffix):
        return Company.objects.create(
            person=Person.objects.create(
                identification=f"17900000010{suffix}", person_type="LEGAL", full_name=f"Empresa {suffix}",
            ),
            commercial_name=f"Empresa {suffix}",
        )

    def sale_dto(self, **overrides):
        data = dict(
            company_id=self.company.pk,
            branch_id=self.branch.pk,
            customer_id=self.customer.pk,
            warehouse_id=self.warehouse.pk,
            issue_date=date.today(),
            notes="integridad",
            details=[SaleDetailDTO(product_id=self.product.pk, quantity=Decimal("1"), unit_price=Decimal("1"))],
        )
        data.update(overrides)
        return SaleCreateDTO(**data)

    def purchase_dto(self, **overrides):
        data = dict(
            company_id=self.company.pk,
            branch_id=self.branch.pk,
            supplier_id=self.supplier.pk,
            issue_date=date.today(),
            notes="integridad",
            details=[PurchaseDetailDTO(product_id=self.product.pk, quantity=Decimal("1"), unit_price=Decimal("1"))],
        )
        data.update(overrides)
        return PurchaseCreateDTO(**data)

    def test_sale_creation_rejects_branch_from_other_company(self):
        with self.assertRaises(ValidationError):
            CreateSale.execute(self.sale_dto(branch_id=self.other_branch.pk))

    def test_sale_creation_rejects_warehouse_from_other_company(self):
        with self.assertRaises(ValidationError):
            CreateSale.execute(self.sale_dto(warehouse_id=self.other_warehouse.pk))

    def test_sale_creation_rejects_warehouse_from_other_branch(self):
        with self.assertRaises(ValidationError):
            CreateSale.execute(self.sale_dto(warehouse_id=self.other_branch_warehouse.pk))

    def test_sale_creation_rejects_product_from_other_company(self):
        with self.assertRaises(ValidationError):
            CreateSale.execute(self.sale_dto(details=[SaleDetailDTO(product_id=self.other_product.pk, quantity=Decimal("1"), unit_price=Decimal("1"))]))

    def test_purchase_creation_rejects_product_from_other_company(self):
        with self.assertRaises(ValidationError):
            CreatePurchase.execute(self.purchase_dto(details=[PurchaseDetailDTO(product_id=self.other_product.pk, quantity=Decimal("1"), unit_price=Decimal("1"))]))

    def test_stock_rejects_incoherent_company_branch_warehouse_product(self):
        with self.assertRaises(ValidationError):
            IncreaseStock().execute(
                company=self.company, branch=self.branch, warehouse=self.other_warehouse,
                product=self.other_product, movement_type=MovementType.ADJUSTMENT_IN,
                quantity=Decimal("1"),
            )

    def test_stock_movement_rejects_incoherent_company_branch_warehouse_product(self):
        with self.assertRaises(ValidationError):
            CreateStockMovement().execute(
                company=self.company, branch=self.branch, warehouse=self.other_warehouse,
                product=self.other_product, movement_type=MovementType.ADJUSTMENT_IN,
                quantity=Decimal("1"),
            )

    def test_transfer_creation_already_rejects_cross_company_warehouses(self):
        dto = TransferCreateDTO(
            company_id=self.company.pk,
            branch_id=self.branch.pk,
            source_warehouse_id=self.warehouse.pk,
            destination_warehouse_id=self.other_warehouse.pk,
            issue_date=date.today(),
            notes="integridad",
            details=[TransferDetailDTO(product_id=self.product.pk, quantity=Decimal("1"))],
        )
        with self.assertRaises(ValueError):
            CreateTransfer.execute(dto)


    def test_transfer_rejects_foreign_product_without_residual_document_or_lines(self):
        destination = Warehouse.objects.create(
            company=self.company, branch=self.branch, code="DEST", name="Destino",
        )
        dto = TransferCreateDTO(
            company_id=self.company.pk,
            branch_id=self.branch.pk,
            source_warehouse_id=self.warehouse.pk,
            destination_warehouse_id=destination.pk,
            issue_date=date.today(),
            notes="foreign-product-regression",
            details=[
                TransferDetailDTO(product_id=self.product.pk, quantity=Decimal("1")),
                TransferDetailDTO(product_id=self.other_product.pk, quantity=Decimal("1")),
            ],
        )
        with self.assertRaisesMessage(
            ValidationError, "El producto no pertenece a la empresa indicada.",
        ):
            CreateTransfer.execute(dto)
        self.assertEqual(Transfer.objects.filter(company=self.company).count(), 0)
        self.assertEqual(TransferDetail.objects.count(), 0)
