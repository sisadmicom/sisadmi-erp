from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Sum

from core.exceptions.inventory import InventoryException
from core.services.document_service import DocumentService

from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.movement.stock_movement_reversal_service import (
    StockMovementReversalService,
)


class TransferCancellationService:

    @staticmethod
    @transaction.atomic
    def cancel(transfer, user=None):
        DocumentService.ensure_can_cancel(transfer)
        content_type = ContentType.objects.get_for_model(transfer)
        historical = StockMovement.objects.filter(
            content_type=content_type, object_id=transfer.pk,
            reverses__isnull=True,
            movement_type__in=(MovementType.TRANSFER_IN, MovementType.TRANSFER_OUT),
        )
        transfer_in = list(historical.filter(movement_type=MovementType.TRANSFER_IN).order_by("id"))
        transfer_out = list(historical.filter(movement_type=MovementType.TRANSFER_OUT).order_by("id"))
        if not transfer_in or not transfer_out:
            raise InventoryException("La transferencia no tiene historia de inventario completa.")
        in_totals = dict(historical.filter(movement_type=MovementType.TRANSFER_IN).values("product_id").annotate(total=Sum("quantity")).values_list("product_id", "total"))
        out_totals = dict(historical.filter(movement_type=MovementType.TRANSFER_OUT).values("product_id").annotate(total=Sum("quantity")).values_list("product_id", "total"))
        if in_totals != out_totals:
            raise InventoryException("La historia de inventario de la transferencia es inconsistente.")
        for movement in transfer_in:
            StockMovementReversalService.reverse(movement=movement, reversal_type=MovementType.RETURN_OUT, user=user)
        for movement in transfer_out:
            StockMovementReversalService.reverse(movement=movement, reversal_type=MovementType.RETURN_IN, user=user)
        return DocumentService.cancel(document=transfer, user=user)
