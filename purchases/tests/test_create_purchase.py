#purchases/purchases/tests/test_create_purchase.py
from decimal import Decimal
from datetime import date

from django.test import TestCase

from purchases.services.purchase_creator import PurchaseCreator
from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.models import Company, Branch, Sequence
from people.models import Supplier
from catalog.models import Product

from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.models import Purchase
from purchases.services.purchase_service import PurchaseService
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
            document_type=DocumentType.objects.get(code=DocumentTypeCodes.PURCHASE_INVOICE),
            name="Compras",
            prefix="OC-",
            series="001",
            next_number=1,
            padding=6,
        )

    def test_creator_persists_document_type(self):

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

        purchase = PurchaseCreator.create(dto)
        purchase.refresh_from_db()
        self.assertEqual(purchase.document_type.code, "PURCHASE_INVOICE")

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

    def test_create_purchase_calculates_discounted_commercial_amounts(self):

        dto = PurchaseCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            supplier_id=self.supplier.id,
            issue_date=date.today(),
            notes="Compra con descuento",
            details=[
                PurchaseDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("3"),
                    unit_price=Decimal("10"),
                    discount=Decimal("4"),
                )
            ],
        )

        purchase = PurchaseCreator.create(dto)
        detail = purchase.details.get()

        self.assertEqual(detail.subtotal, Decimal("26"))
        self.assertEqual(detail.tax_amount, Decimal("0"))
        self.assertEqual(detail.total, Decimal("26"))
        self.assertEqual(purchase.subtotal, Decimal("26"))
        self.assertEqual(purchase.tax, Decimal("0"))
        self.assertEqual(purchase.total, Decimal("26"))

    def test_create_purchase_aggregates_multiple_lines(self):

        second_product = Product.objects.create(
            company=self.company,
            code="P002",
            name="Segundo producto",
        )
        dto = PurchaseCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            supplier_id=self.supplier.id,
            issue_date=date.today(),
            notes="Compra de varias líneas",
            details=[
                PurchaseDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("2"),
                    unit_price=Decimal("10"),
                    discount=Decimal("1"),
                ),
                PurchaseDetailDTO(
                    product_id=second_product.id,
                    quantity=Decimal("3"),
                    unit_price=Decimal("5"),
                    discount=Decimal("0"),
                ),
            ],
        )

        purchase = PurchaseCreator.create(dto)

        self.assertEqual(purchase.details.count(), 2)
        self.assertEqual(purchase.subtotal, Decimal("34"))
        self.assertEqual(purchase.tax, Decimal("0"))
        self.assertEqual(purchase.total, Decimal("34"))

    def test_purchase_service_calculate_recalculates_lines_and_preserves_tax(self):

        dto = PurchaseCreateDTO(
            company_id=self.company.id,
            branch_id=self.branch.id,
            supplier_id=self.supplier.id,
            issue_date=date.today(),
            notes="Compra para recalcular",
            details=[
                PurchaseDetailDTO(
                    product_id=self.product.id,
                    quantity=Decimal("2"),
                    unit_price=Decimal("10"),
                    discount=Decimal("2"),
                )
            ],
        )
        purchase = PurchaseCreator.create(dto)
        detail = purchase.details.get()
        detail.subtotal = Decimal("999")
        detail.tax_amount = Decimal("2.70")
        detail.total = Decimal("999")
        detail.save(update_fields=["subtotal", "tax_amount", "total", "updated_at"])

        result = PurchaseService.calculate(purchase)
        detail.refresh_from_db()

        self.assertIs(result, purchase)
        self.assertEqual(detail.subtotal, Decimal("18"))
        self.assertEqual(detail.tax_amount, Decimal("2.70"))
        self.assertEqual(detail.total, Decimal("20.70"))
        self.assertEqual(result.subtotal, Decimal("18"))
        self.assertEqual(result.tax, Decimal("2.70"))
        self.assertEqual(result.total, Decimal("20.70"))

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

