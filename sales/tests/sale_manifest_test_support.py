"""Fixtures for the C-06 SaleMovement contract; no production fallback."""
from datetime import date
from decimal import Decimal

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Product
from core.constants.document_type_codes import DocumentTypeCodes
from core.models import Branch, Company, DocumentType, Sequence
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from people.models import Customer, Person
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.use_cases.create_sale import CreateSale
from sales.use_cases.confirm_sale import ConfirmSale


class SaleManifestFixture(TestCase):
    def setUp(self):
        super().setUp()
        sale_type = DocumentType.objects.get(code=DocumentTypeCodes.SALES_INVOICE)
        self.company = Company.objects.create(
            person=Person.objects.create(identification="C06-COMPANY", person_type="LEGAL", full_name="C06"),
            commercial_name="C06",
        )
        self.branch = Branch.objects.create(company=self.company, code="001", name="Matriz")
        self.warehouse = Warehouse.objects.create(company=self.company, branch=self.branch, code="W1", name="Principal")
        Sequence.objects.create(company=self.company, branch=self.branch, document_type=sale_type,
                                name="Ventas C06", prefix="V06-", next_number=1)
        self.customer = Customer.objects.create(
            person=Person.objects.create(identification="C06-CUSTOMER", person_type="NATURAL", full_name="Cliente C06"),
        )
        self.product = Product.objects.create(company=self.company, code="P1", name="Producto 1")
        self.product2 = Product.objects.create(company=self.company, code="P2", name="Producto 2")
        for product in (self.product, self.product2):
            Stock.objects.create(company=self.company, branch=self.branch, warehouse=self.warehouse,
                                 product=product, quantity=Decimal("100"), reserved_quantity=Decimal("0"))

    def make_sale(self, lines=None):
        lines = lines or [(self.product, Decimal("5"), Decimal("10"))]
        sale = CreateSale.execute(SaleCreateDTO(
            company_id=self.company.pk, branch_id=self.branch.pk, customer_id=self.customer.pk,
            warehouse_id=self.warehouse.pk, issue_date=date(2026, 9, 15), notes="Venta C06",
            details=[SaleDetailDTO(product_id=p.pk, quantity=q, unit_price=price, discount=Decimal("0"))
                     for p, q, price in lines],
        ))
        return sale

    def confirm(self, sale):
        ConfirmSale.execute(sale_id=sale.pk, user=None)
        sale.refresh_from_db()
        return sale

    def originals(self, sale):
        return StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(sale), object_id=sale.pk,
            movement_type=MovementType.SALE, reverses__isnull=True,
        ).order_by("pk")

    def model(self):
        try:
            return apps.get_model("sales", "SaleMovement")
        except LookupError:
            return None

    def require_model(self):
        model = self.model()
        self.assertIsNotNone(model, "SaleMovement requerido por el contrato C-06")
        return model
