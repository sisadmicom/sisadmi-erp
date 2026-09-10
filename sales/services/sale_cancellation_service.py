from django.db import transaction

from core.services.document_service import DocumentService

from inventory.constants.movement_type import MovementType
from inventory.services.stock.increase_stock import IncreaseStock

from sales.services.sale_validator import SaleValidator


class SaleCancellationService:

    @staticmethod
    @transaction.atomic
    def cancel(
        sale,
        user=None,
    ):

        DocumentService.ensure_can_cancel(sale)

        SaleValidator.validate_cancellation(
            sale
        )

        increase = IncreaseStock()

        for detail in sale.details.all():

            increase.execute(
                company=sale.company,
                branch=sale.branch,
                warehouse=sale.warehouse,
                product=detail.product,
                quantity=detail.quantity,
                movement_type=MovementType.RETURN_IN,
                unit_cost=detail.unit_price,
                document=sale,
                notes=f"Anulación venta {sale.number}",
                user=user,
            )

        return DocumentService.cancel(
            document=sale,
            user=user,
        )
