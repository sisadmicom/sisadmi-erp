from datetime import date
from decimal import Decimal

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from core.constants.document_type_codes import DocumentTypeCodes
from core.models import Branch, Company, DocumentType, Sequence
from catalog.models import Product
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from people.models import Person, Supplier
from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.models import Purchase
from purchases.use_cases.create_purchase import CreatePurchase
from purchases.use_cases.confirm_purchase import ConfirmPurchase


class PurchaseManifestFixture(TestCase):
    def setUp(self):
        person = Person.objects.create(
            identification="1790000001001", person_type="LEGAL", full_name="Empresa C05"
        )
        self.company = Company.objects.create(person=person, commercial_name="Empresa C05")
        self.branch = Branch.objects.create(company=self.company, code="001", name="Matriz")
        self.warehouse_a = Warehouse.objects.create(
            company=self.company, branch=self.branch, code="A", name="Bodega A", is_main=True
        )
        self.warehouse_b = Warehouse.objects.create(
            company=self.company, branch=self.branch, code="B", name="Bodega B", is_main=False
        )
        supplier_person = Person.objects.create(
            identification="0999999999001", person_type="LEGAL", full_name="Proveedor C05"
        )
        self.supplier = Supplier.objects.create(person=supplier_person)
        self.product = Product.objects.create(company=self.company, code="P001", name="Producto C05")
        self.product_2 = Product.objects.create(company=self.company, code="P002", name="Producto C05-2")
        dtype = DocumentType.objects.get(code=DocumentTypeCodes.PURCHASE_INVOICE)
        self.sequence = Sequence.objects.create(
            company=self.company, branch=self.branch, document_type=dtype,
            name="Compras C05", prefix="C5-", series="001", next_number=1, padding=6,
        )

    def make_purchase(self, details=None):
        details = details or [(self.product, Decimal("5"), Decimal("10"))]
        dto = PurchaseCreateDTO(
            company_id=self.company.id, branch_id=self.branch.id, supplier_id=self.supplier.id,
            issue_date=date.today(), notes="C05", details=[
                PurchaseDetailDTO(product_id=p.id, quantity=q, unit_price=price)
                for p, q, price in details
            ],
        )
        return CreatePurchase.execute(dto)

    def confirm(self, purchase):
        return ConfirmPurchase.execute(purchase_id=purchase.pk, user=None)

    def model(self, testcase):
        try:
            model = apps.get_model("purchases", "PurchaseMovement")
        except LookupError:
            model = None
        testcase.assertIsNotNone(model, "PurchaseMovement requerido por el contrato C-05")
        return model

    def original_movements(self, purchase):
        return StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(Purchase),
            object_id=purchase.pk, movement_type=MovementType.PURCHASE,
            reverses__isnull=True,
        ).order_by("pk")

    def manifest_rows(self, purchase, testcase):
        model = self.model(testcase)
        if model is None:
            return model.objects.none()
        return model.objects.filter(purchase=purchase).order_by("pk")

    def stock_snapshot(self, purchase):
        return list(Stock.objects.filter(company=purchase.company, branch=purchase.branch).order_by("pk").values_list("warehouse_id", "product_id", "quantity"))
