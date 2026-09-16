"""Dataset mínimo C-01; imports de la feature diferidos para recolectar todo el RED."""
from datetime import date
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from catalog.models import Product
from core.exceptions.base import BusinessException
from core.models import Branch, Company, DocumentType, Sequence
from inventory.models import Stock, StockMovement, Warehouse
from people.models import Person


REJECTIONS = (ValidationError, BusinessException, ValueError)
QUANTITY = Decimal("0.004000")
TYPE_CODES = {direction: f"INVENTORY_ADJUSTMENT_{direction}" for direction in ("IN", "OUT")}


class AdjustmentDataset:
    def setUp(self):
        super().setUp()
        self.company = self.make_company("A")
        self.branch = Branch.objects.create(company=self.company, code="001", name="Matriz")
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, code="W1", name="Principal",
        )
        self.product = Product.objects.create(company=self.company, code="P1", name="Uno")
        self.second_product = Product.objects.create(company=self.company, code="P2", name="Dos")

    def make_company(self, suffix):
        return Company.objects.create(person=Person.objects.create(
            identification=f"C01-{suffix}", person_type="LEGAL", full_name=f"Empresa {suffix}",
        ))

    def stock(self, product=None, quantity="10", reserved="0"):
        return Stock.objects.create(
            company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=product or self.product, quantity=Decimal(quantity),
            reserved_quantity=Decimal(reserved),
        )


class AdjustmentFixture(AdjustmentDataset):
    def setUp(self):
        super().setUp()
        # No skips/fallbacks productivos: cada método se recolecta y falla por
        # feature ausente. Estos imports son el contrato público previsto.
        from inventory.models import InventoryAdjustment, InventoryAdjustmentDetail
        from inventory.dto.inventory_adjustment_create_dto import InventoryAdjustmentCreateDTO
        from inventory.dto.inventory_adjustment_detail_dto import InventoryAdjustmentDetailDTO
        from inventory.use_cases.create_inventory_adjustment import CreateInventoryAdjustment
        from inventory.use_cases.confirm_inventory_adjustment import ConfirmInventoryAdjustment
        from inventory.use_cases.cancel_inventory_adjustment import CancelInventoryAdjustment

        self.Adjustment = InventoryAdjustment
        self.Detail = InventoryAdjustmentDetail
        self.CreateDTO = InventoryAdjustmentCreateDTO
        self.DetailDTO = InventoryAdjustmentDetailDTO
        self.Creator = CreateInventoryAdjustment
        self.Confirmer = ConfirmInventoryAdjustment
        self.Canceller = CancelInventoryAdjustment
        self.types = {}
        self.sequences = {}
        for direction, code in TYPE_CODES.items():
            # Aísla lifecycle del seed y soporta flush de TransactionTestCase.
            # El catálogo REAL se exige por separado, sin estos defaults.
            self.types[direction], _ = DocumentType.objects.get_or_create(
                code=code, defaults=dict(
                    name=f"Ajuste {direction}", category="INVENTORY", line_behavior="QUANTITY",
                    requires_detail=True, affects_inventory=True,
                    inventory_behavior=direction, can_issue_electronic=False, is_active=True,
                ),
            )
            self.sequences[direction] = Sequence.objects.create(
                company=self.company, branch=self.branch, document_type=self.types[direction],
                name=f"Ajustes {direction}", prefix=f"AJ-{direction}-", next_number=1,
            )

    def dto(self, **overrides):
        data = dict(
            company_id=self.company.pk, branch_id=self.branch.pk,
            warehouse_id=self.warehouse.pk, issue_date=date(2026, 9, 15),
            notes="Corrección operacional documentada",
            details=[self.line(self.product)],
        )
        data.update(overrides)
        return self.CreateDTO(**data)

    def line(self, product, quantity=QUANTITY):
        return self.DetailDTO(product_id=product.pk, quantity=Decimal(quantity))

    def create(self, direction="IN", **overrides):
        return getattr(self.Creator, f"create_{direction.lower()}")(self.dto(**overrides))

    def confirm(self, adjustment):
        return self.Confirmer.execute(adjustment_id=adjustment.pk, user=None)

    def cancel(self, adjustment):
        return self.Canceller.execute(adjustment_id=adjustment.pk, user=None)

    def movements(self, adjustment):
        return StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(self.Adjustment),
            object_id=adjustment.pk,
        ).order_by("pk")

    def snapshot(self, adjustment):
        return dict(
            document=self.Adjustment.objects.values(
                "status", "number", "confirmed_at", "confirmed_by_id", "cancelled_at", "cancelled_by_id",
            ).get(pk=adjustment.pk),
            stocks=list(Stock.objects.order_by("pk").values()),
            movements=list(StockMovement.objects.order_by("pk").values()),
            sequences=list(Sequence.objects.order_by("pk").values("pk", "next_number")),
        )

    def assert_creation_rejected(self, direction="IN", **overrides):
        before_stock = list(Stock.objects.order_by("pk").values())
        before_sequences = list(Sequence.objects.order_by("pk").values("pk", "next_number"))
        with self.assertRaises(REJECTIONS):
            self.create(direction, **overrides)
        self.assertEqual(self.Adjustment.objects.count(), 0)
        self.assertEqual(self.Detail.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertEqual(list(Stock.objects.order_by("pk").values()), before_stock)
        self.assertEqual(list(Sequence.objects.order_by("pk").values("pk", "next_number")), before_sequences)

    def assert_operation_rejected(self, adjustment, operation):
        before = self.snapshot(adjustment)
        with self.assertRaises(REJECTIONS):
            operation(adjustment)
        self.assertEqual(self.snapshot(adjustment), before)
