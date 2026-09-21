"""C-03: fixtures reales; ninguna API futura se importa durante colección.

El catálogo PURCHASE_RETURN debe venir de migraciones, nunca de este soporte.
Las excepciones aceptadas son las familias de dominio/lifecycle ya públicas.
ImportError, errores SQL y errores de programación nunca cuentan como rechazo.
"""
from datetime import date
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import tag

from catalog.models import Product
from core.constants.document_type_codes import DocumentTypeCodes
from core.exceptions.base import BusinessException
from core.models import Branch, Company, DocumentType, Sequence
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from people.models import Person, Supplier
from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.models import Purchase
from purchases.use_cases.create_purchase import CreatePurchase
from purchases.use_cases.confirm_purchase import ConfirmPurchase


REJECTIONS = (ValidationError, BusinessException, ValueError)
MONEY_FIELDS = ("discount", "subtotal", "tax_amount", "total")


def return_api():
    from purchases.dto.purchase_return_create_dto import PurchaseReturnCreateDTO
    from purchases.dto.purchase_return_detail_dto import PurchaseReturnDetailDTO
    from purchases.use_cases.create_purchase_return import CreatePurchaseReturn
    from purchases.use_cases.confirm_purchase_return import ConfirmPurchaseReturn
    from purchases.use_cases.cancel_purchase_return import CancelPurchaseReturn
    return (PurchaseReturnCreateDTO, PurchaseReturnDetailDTO, CreatePurchaseReturn,
            ConfirmPurchaseReturn, CancelPurchaseReturn)


def return_models():
    from purchases.models.purchase_return import PurchaseReturn
    from purchases.models.purchase_return_detail import PurchaseReturnDetail
    return PurchaseReturn, PurchaseReturnDetail


def movements(document, movement_type=None):
    rows = StockMovement.objects.filter(
        content_type=ContentType.objects.get_for_model(document), object_id=document.pk,
    ).order_by("pk")
    return rows if movement_type is None else rows.filter(movement_type=movement_type)


def persisted_state():
    """Incluye snapshots/totales y auditoría: detecta cualquier escritura parcial."""
    Return, Detail = return_models()
    return {
        model._meta.label: list(model.objects.order_by("pk").values())
        for model in (Purchase, Return, Detail, Sequence, Stock, StockMovement)
    }


@tag("c03_purchase_return")
class PurchaseReturnFixture:
    """Mixin independiente de TestCase para compartir con TransactionTestCase."""

    def setUp(self):
        super().setUp()
        # TransactionTestCase puede haber vaciado los datos de migraciones.
        # Solo se repone aquí el catálogo preexistente, nunca la feature futura.
        purchase_type, _ = DocumentType.objects.get_or_create(
            code=DocumentTypeCodes.PURCHASE_INVOICE,
            defaults=dict(name="Factura de compra", category="PURCHASES",
                          line_behavior="COMMERCIAL", requires_detail=True,
                          affects_inventory=True, inventory_behavior="IN",
                          can_issue_electronic=False),
        )
        self.company = Company.objects.create(person=Person.objects.create(
            identification="C03-COMPANY", person_type="LEGAL", full_name="Empresa C03"))
        self.branch = Branch.objects.create(company=self.company, code="001", name="Matriz")
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, code="A", name="Histórica A", is_main=True)
        self.supplier = Supplier.objects.create(person=Person.objects.create(
            identification="C03-SUPPLIER", person_type="LEGAL", full_name="Proveedor C03"))
        self.product = Product.objects.create(company=self.company, code="P1", name="Uno")
        self.product2 = Product.objects.create(company=self.company, code="P2", name="Dos")
        self.sequence = Sequence.objects.create(
            company=self.company, branch=self.branch, document_type=purchase_type,
            name="Compras", prefix="COM-", next_number=1)
        self.purchase = self.make_purchase()

    def make_purchase(self, quantity="10", *, confirm=True, lines=None, initial=None):
        if initial is not None:
            Stock.objects.create(company=self.company, branch=self.branch,
                                 warehouse=self.warehouse, product=self.product,
                                 quantity=Decimal(initial))
        details = lines if lines is not None else [
            PurchaseDetailDTO(product_id=self.product.pk, quantity=Decimal(quantity),
                              unit_price=Decimal("10"))]
        purchase = CreatePurchase.execute(PurchaseCreateDTO(
            company_id=self.company.pk, branch_id=self.branch.pk,
            supplier_id=self.supplier.pk, issue_date=date(2026, 9, 19), notes="Compra C03",
            details=details))
        if confirm:
            ConfirmPurchase.execute(purchase_id=purchase.pk, user=None)
            purchase.refresh_from_db()
        return purchase

    def two_line_purchase(self):
        return self.make_purchase(lines=[
            PurchaseDetailDTO(self.product.pk, Decimal("10"), Decimal("10")),
            PurchaseDetailDTO(self.product2.pk, Decimal("10"), Decimal("12")),
        ])

    def monetary_purchase(self):
        purchase = self.make_purchase(quantity="3", confirm=False, lines=[
            PurchaseDetailDTO(self.product.pk, Decimal("3"), Decimal("0.34"), Decimal("0.01"))])
        # Purchase no calcula impuestos hoy. Representa historia agregada válida,
        # persistida ANTES de confirmar; los movimientos siguen siendo reales.
        purchase.details.update(tax_amount=Decimal("0.01"), total=Decimal("1.02"))
        Purchase.objects.filter(pk=purchase.pk).update(tax=Decimal("0.01"), total=Decimal("1.02"))
        ConfirmPurchase.execute(purchase_id=purchase.pk, user=None)
        purchase.refresh_from_db()
        return purchase

    def return_sequence(self):
        document_type = DocumentType.objects.get(code=DocumentTypeCodes.PURCHASE_RETURN)
        sequence, _ = Sequence.objects.get_or_create(
            company=self.company, branch=self.branch, document_type=document_type,
            defaults=dict(name="Devoluciones de compra", prefix="DC-", next_number=1))
        return sequence

    def dto(self, quantity="3", *, purchase=None, details=None, notes=""):
        DTO, Line, *_ = return_api()
        purchase = self.purchase if purchase is None else purchase
        if details is None:
            details = [Line(purchase_detail_id=purchase.details.get().pk, quantity=Decimal(quantity))]
        return DTO(purchase_id=purchase.pk, issue_date=purchase.issue_date, notes=notes, details=details)

    def make_return(self, quantity="3", *, purchase=None, details=None):
        dto = self.dto(quantity, purchase=purchase, details=details)
        self.return_sequence()
        return return_api()[2].execute(dto)

    def confirm_return(self, document):
        return_api()[3].execute(purchase_return_id=document.pk, user=None)
        document.refresh_from_db()
        return document

    def cancel_return(self, document):
        return_api()[4].execute(purchase_return_id=document.pk, user=None)
        document.refresh_from_db()
        return document

    def stock(self, product=None):
        return Stock.objects.get(company=self.company, branch=self.branch,
                                 warehouse=self.warehouse, product=product or self.product)

    def assert_rejected_unchanged(self, operation):
        before = persisted_state()
        with self.assertRaises(REJECTIONS) as caught:
            operation()
        self.assertTrue(str(caught.exception))
        self.assertEqual(persisted_state(), before)

    def assert_reversal(self, document, original, reversal_type):
        reversal = StockMovement.objects.get(reverses=original)
        self.assertEqual(reversal.document, document)
        self.assertEqual(reversal.movement_type, reversal_type)
        for field in ("quantity", "unit_cost", "company_id", "branch_id",
                      "warehouse_id", "product_id", "content_type_id", "object_id"):
            self.assertEqual(getattr(reversal, field), getattr(original, field), field)
        return reversal

    def assert_reconciled(self, purchase):
        _, Detail = return_models()
        source = purchase.details.get()
        rows = list(Detail.objects.filter(purchase_detail=source,
                                         purchase_return__status="CONFIRMED"))
        self.assertEqual(sum((row.quantity for row in rows), Decimal("0")), source.quantity)
        for field in MONEY_FIELDS:
            self.assertEqual(sum((getattr(row, field) for row in rows), Decimal("0")),
                             getattr(source, field), field)

    def new_context(self):
        company = Company.objects.create(person=Person.objects.create(
            identification="C03-OTHER", person_type="LEGAL", full_name="Otra empresa"))
        branch = Branch.objects.create(company=company, code="002", name="Otra")
        warehouse = Warehouse.objects.create(company=company, branch=branch,
                                             code="OTHER", name="Otra", is_main=True)
        product = Product.objects.create(company=company, code="OTHER", name="Ajeno")
        return company, branch, warehouse, product
