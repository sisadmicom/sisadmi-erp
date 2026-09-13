from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from purchases.models import Purchase

from core.exceptions.inventory import InventoryException
from core.services.document_service import DocumentService

from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.movement.stock_movement_reversal_service import (
    StockMovementReversalService,
)


class PurchaseCancellationService:

    @staticmethod
    @transaction.atomic
    def cancel(
        purchase_id,
        user=None,
    ):

        purchase = Purchase.objects.select_for_update().get(pk=purchase_id)

        DocumentService.ensure_can_cancel(purchase)

        movements = StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(purchase),
            object_id=purchase.pk,
            movement_type=MovementType.PURCHASE,
            reverses__isnull=True,
        ).order_by("id")

        if not movements.exists():
            raise InventoryException(
                "La compra no tiene movimientos históricos PURCHASE para revertir."
            )

        for movement in movements:
            StockMovementReversalService.reverse(
                movement=movement,
                reversal_type=MovementType.RETURN_OUT,
                user=user,
            )

        return DocumentService.cancel(
            document=purchase,
            user=user,
        )
