from django.db import transaction

from core.exceptions.inventory import InventoryException
from core.services.document_service import DocumentService

from inventory.constants.movement_type import MovementType
from inventory.services.movement.stock_movement_reversal_service import (
    StockMovementReversalService,
)

from sales.models import Sale
from sales.services.sale_history import validated_sale_movements


class SaleCancellationService:

    @staticmethod
    @transaction.atomic
    def cancel(
        sale_id,
        user=None,
    ):

        sale = Sale.objects.select_for_update().get(pk=sale_id)

        DocumentService.ensure_can_cancel(sale)

        from sales.models import SalesReturn
        if SalesReturn.objects.filter(sale_id=sale.pk, status="CONFIRMED").exists():
            raise InventoryException("No se puede cancelar una venta con devoluciones confirmadas.")

        movements = validated_sale_movements(sale, lock=True)

        for movement in movements:
            StockMovementReversalService.reverse(
                movement=movement,
                reversal_type=MovementType.RETURN_IN,
                user=user,
            )

        return DocumentService.cancel(
            document=sale,
            user=user,
        )
