# purchases/tests/test_confirm_purchase.py

from decimal import Decimal
from datetime import date

from django.test import TestCase

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.models import Company, Branch, Sequence
from people.models import Person, Supplier
from catalog.models import Product

from inventory.models import Warehouse

from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.use_cases.create_purchase import CreatePurchase
from purchases.use_cases.confirm_purchase import ConfirmPurchase

class ConfirmPurchaseTest(TestCase):

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

        supplier_person = Person.objects.create(
            identification="0999999999001",
            person_type="LEGAL",
            full_name="Proveedor Test",
        )

        self.supplier = Supplier.objects.create(
            person=supplier_person,
        )

        self.product = Product.objects.create(
            company=self.company,
            code="P001",
            name="Producto Test",
        )

        Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            document_type=DocumentType.objects.get(code=DocumentTypeCodes.PURCHASE_INVOICE),
            name="Compras",
            prefix="OC-",
            series="001",
            next_number=1,
            padding=6,
        )

        dto = PurchaseCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            supplier_id=self.supplier.id,
            issue_date=date.today(),
            notes="Compra",
            details=[
                PurchaseDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("5"),
                    unit_price=Decimal("10"),
                )
            ],
        )

        self.purchase = CreatePurchase.execute(dto)

    def test_confirm_purchase(self):

        purchase = ConfirmPurchase.execute(
            purchase_id=self.purchase.id,
            user=None,
        )

        purchase.refresh_from_db()

        self.assertTrue(
            purchase.is_confirmed()
        )

    def test_confirm_purchase_twice(self):

        ConfirmPurchase.execute(
            purchase_id=self.purchase.id,
            user=None,
        )

        with self.assertRaises(Exception):

            ConfirmPurchase.execute(
                purchase_id=self.purchase.id,
                user=None,
            )

    def test_confirm_purchase_without_details(self):

        self.purchase.details.all().delete()

        with self.assertRaises(Exception):

            ConfirmPurchase.execute(
                purchase_id=self.purchase.id,
                user=None,
            )