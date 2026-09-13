# purchases/tests/test_confirm_purchase.py

from decimal import Decimal
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from django.test import TestCase

from core.models.document_type import DocumentType
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.document_status import DocumentStatus
from core.models import Company, Branch, Sequence
from people.models import Person, Supplier
from catalog.models import Product

from core.exceptions.inventory import InventoryException
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.stock import IncreaseStock
from purchases.models import Purchase
from purchases.services.purchase_service import PurchaseService

from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.use_cases.create_purchase import CreatePurchase
from purchases.use_cases.confirm_purchase import ConfirmPurchase


def purchase_lifecycle_snapshot(purchase, sequence):
    """Estado persistido que una operación rechazada debe preservar completo."""
    document = Purchase.objects.values(
        "status", "number", "confirmed_at", "confirmed_by_id",
        "cancelled_at", "cancelled_by_id",
    ).get(pk=purchase.pk)
    return {
        **document,
        "next_number": Sequence.objects.get(pk=sequence.pk).next_number,
        "stocks": list(Stock.objects.filter(
            company_id=purchase.company_id, branch_id=purchase.branch_id,
        ).order_by("pk").values("product_id", "warehouse_id", "quantity", "reserved_quantity")),
        "movements": list(StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(Purchase),
            object_id=purchase.pk,
        ).order_by("pk").values(
            "id", "movement_type", "quantity", "unit_cost", "reverses_id",
            "warehouse_id", "product_id", "created_by_id",
        )),
    }

class PurchaseFixture:
    """Dataset de confirmación existente, reutilizado por TransactionTestCase."""

    def setUp(self):
        super().setUp()
        document_type, _ = DocumentType.objects.get_or_create(
            code=DocumentTypeCodes.PURCHASE_INVOICE,
            defaults={
                "name": "Factura de compra", "category": "PURCHASES",
                "line_behavior": "COMMERCIAL", "requires_detail": True,
                "affects_inventory": True, "inventory_behavior": "IN",
                "can_issue_electronic": False,
            },
        )

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

        self.sequence = Sequence.objects.create(
            company=self.company,
            branch=self.branch,
            document_type=document_type,
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


class ConfirmPurchaseTest(PurchaseFixture, TestCase):
    maxDiff = None

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

        with self.assertRaisesMessage(ValueError, "Solo se pueden confirmar documentos en borrador."):

            ConfirmPurchase.execute(
                purchase_id=self.purchase.id,
                user=None,
            )
        self.purchase.status = DocumentStatus.CANCELLED
        self.purchase.save(update_fields=["status"])
        with self.assertRaisesMessage(ValueError, "Solo se pueden confirmar documentos en borrador."):
            ConfirmPurchase.execute(purchase_id=self.purchase.id, user=None)


    def test_confirm_purchase_without_details(self):

        self.purchase.details.all().delete()

        with self.assertRaises(Exception):

            ConfirmPurchase.execute(
                purchase_id=self.purchase.id,
                user=None,
            )

    def test_stale_purchase_cannot_repeat_confirmation(self):
        first_user = get_user_model().objects.create_user(username="purchase-first")
        other_user = get_user_model().objects.create_user(username="purchase-stale")
        stale = Purchase.objects.get(pk=self.purchase.pk)
        self.assertEqual(stale.status, DocumentStatus.DRAFT)
        ConfirmPurchase.execute(purchase_id=self.purchase.pk, user=first_user)
        before = purchase_lifecycle_snapshot(self.purchase, self.sequence)

        # Firma real actual de la facade: la instancia retenida no debe gobernar.
        try:
            PurchaseService.confirm(purchase_id=stale.pk, user=other_user)
        except (ValueError, InventoryException) as error:
            outcome = (type(error).__name__, str(error))
        else:
            outcome = ("success", "")

        self.assertEqual(
            {"outcome": outcome, **purchase_lifecycle_snapshot(self.purchase, self.sequence)},
            {
                "outcome": ("ValueError", "Solo se pueden confirmar documentos en borrador."),
                **before,
            },
        )

    def test_confirmation_effect_failure_rolls_back_entire_operation(self):
        user = get_user_model().objects.create_user(username="purchase-rollback")
        before = purchase_lifecycle_snapshot(self.purchase, self.sequence)
        observed = []
        increase = IncreaseStock.execute

        def increase_then_fail(service, **kwargs):
            # Se ejecutan stock y movimiento reales; solo se inyecta el fallo.
            increase(service, **kwargs)
            observed.append(purchase_lifecycle_snapshot(self.purchase, self.sequence))
            raise RuntimeError("Fallo posterior al efecto de compra.")

        with patch.object(IncreaseStock, "execute", new=increase_then_fail):
            with self.assertRaisesMessage(RuntimeError, "Fallo posterior al efecto de compra."):
                ConfirmPurchase.execute(purchase_id=self.purchase.pk, user=user)

        self.assertEqual(len(observed), 1)
        checkpoint = observed[0]
        self.assertEqual(checkpoint["status"], DocumentStatus.CONFIRMED)
        self.assertTrue(checkpoint["number"])
        self.assertIsNotNone(checkpoint["confirmed_at"])
        self.assertEqual(checkpoint["confirmed_by_id"], user.pk)
        self.assertEqual(checkpoint["next_number"], before["next_number"] + 1)
        self.assertEqual([row["quantity"] for row in checkpoint["stocks"]], [Decimal("5")])
        self.assertEqual(
            [(row["movement_type"], row["quantity"]) for row in checkpoint["movements"]],
            [(MovementType.PURCHASE, Decimal("5"))],
        )
        self.assertEqual(purchase_lifecycle_snapshot(self.purchase, self.sequence), before)
