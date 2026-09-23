"""Fixtures for the C-07 SalesReturnMovement RED contract."""
from decimal import Decimal

from django.apps import apps
from django.contrib.contenttypes.models import ContentType

from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement
from inventory.tests.sales_return_test_support import SalesReturnFixture
from datetime import date
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.use_cases.create_sale import CreateSale
from sales.use_cases.confirm_sale import ConfirmSale


class SalesReturnManifestFixture(SalesReturnFixture):
    def require_model(self):
        try:
            model = apps.get_model("sales", "SalesReturnMovement")
        except LookupError:
            model = None
        self.assertIsNotNone(model, "SalesReturnMovement requerido por el contrato C-07")
        return model

    def confirm_return(self, quantity="3", sale_detail_id=None):
        _, _, creator, confirmer, _ = self.api()
        ret = creator.execute(self.dto(quantity=quantity, sale_detail_id=sale_detail_id))
        confirmer.execute(ret.pk, user=None)
        ret.refresh_from_db()
        return ret

    def make_two_line_sale(self, duplicate_product=False):
        second_product = self.product if duplicate_product else self.product2
        Stock.objects.get_or_create(
            company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=second_product,
            defaults={"quantity": Decimal("100"), "reserved_quantity": Decimal("0")},
        )
        sale = CreateSale.execute(SaleCreateDTO(
            company_id=self.company.pk, branch_id=self.branch.pk,
            customer_id=self.customer.pk, warehouse_id=self.warehouse.pk,
            issue_date=date(2026, 9, 15), notes="Venta C07 multilinea",
            details=[
                SaleDetailDTO(product_id=self.product.pk, quantity=Decimal("3"), unit_price=Decimal("10"), discount=Decimal("0")),
                SaleDetailDTO(product_id=second_product.pk, quantity=Decimal("2"), unit_price=Decimal("10"), discount=Decimal("0")),
            ],
        ))
        ConfirmSale.execute(sale_id=sale.pk, user=None)
        return sale

    def originals(self, ret):
        return StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(ret),
            object_id=ret.pk,
            movement_type=MovementType.RETURN_IN,
            reverses__isnull=True,
        ).order_by("pk")

    def manifests(self, ret):
        return self.require_model().objects.filter(sales_return=ret).order_by("pk")

    def create_extra_return_in(self, ret, quantity="1"):
        return StockMovement.objects.create(
            company=self.company,
            branch=self.branch,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal(quantity),
            movement_type=MovementType.RETURN_IN,
            content_type=ContentType.objects.get_for_model(ret),
            object_id=ret.pk,
        )
