#purchases/purchases/tests/test_create_purchase.py
from decimal import Decimal
from datetime import date

from django.test import TestCase

from core.models import Company, Branch, Sequence
from people.models import Supplier
from catalog.models import Product

from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.models import Purchase
from purchases.use_cases.create_purchase import CreatePurchase

from people.models import Person

class CreatePurchaseTest(TestCase):

    def setUp(self):

        company_person = Person.objects.create(
            identification="1790000001001",
            person_type="LEGAL",
            full_name="Empresa Test",
        )

        self.company = Company.objects.create(
            person=company_person,
            commercial_name="Empresa Test"
        )

        self.branch = Branch.objects.create(
            company=self.company,
            code="001",
            name="Matriz"
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
            code="PUR",
            name="Compras",
            prefix="OC-",
            series="001",
            next_number=1,
            padding=6,
        )

    def test_create_purchase(self):

        dto = PurchaseCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            supplier_id=self.supplier.id,
            issue_date=date.today(),
            notes="Compra de prueba",
            details=[
                PurchaseDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("5"),
                    unit_price=Decimal("10"),
                    discount=Decimal("0"),
                )
            ]
        )

        purchase = CreatePurchase.execute(dto)

        self.assertIsNotNone(purchase.id)

        self.assertEqual(
            purchase.details.count(),
            1
        )

        self.assertEqual(
            purchase.subtotal,
            Decimal("50")
        )

        self.assertEqual(
            purchase.total,
            Decimal("50")
        )

    def test_create_purchase_without_details(self):

        dto = PurchaseCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            supplier_id=self.supplier.id,
            issue_date=date.today(),
            notes="",
            details=[]
        )

        with self.assertRaises(Exception):

            CreatePurchase.execute(dto)

    def test_invalid_quantity(self):

        dto = PurchaseCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            supplier_id=self.supplier.id,
            issue_date=date.today(),
            notes="",
            details=[
                PurchaseDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("0"),
                    unit_price=Decimal("10"),
                )
            ]
        )

        with self.assertRaises(Exception):

            CreatePurchase.execute(dto)

