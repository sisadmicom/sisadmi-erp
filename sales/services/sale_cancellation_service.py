from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from core.exceptions.inventory import InventoryException
from core.services.document_service import DocumentService

from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.movement.stock_movement_reversal_service import (
    StockMovementReversalService,
)


class SaleCancellationService:

    @staticmethod
    @transaction.atomic
    def cancel(
        sale,
        user=None,
    ):

        DocumentService.ensure_can_cancel(sale)

        movements = StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(sale),
            object_id=sale.pk,
            movement_type=MovementType.SALE,
            reverses__isnull=True,
        ).order_by("id")

        if not movements.exists():
            raise InventoryException(
                "La venta no tiene movimientos históricos SALE para revertir."
            )

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
