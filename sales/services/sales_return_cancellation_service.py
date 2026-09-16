from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from sales.models import SalesReturn
class SalesReturnCancellationService:
    @staticmethod
    @transaction.atomic
    def execute(sales_return_id,user=None):
        ret=SalesReturn.objects.select_for_update().get(pk=sales_return_id)
        DocumentService.ensure_can_cancel(ret)
        movements=StockMovement.objects.filter(content_type=ContentType.objects.get_for_model(SalesReturn),
            object_id=ret.pk,movement_type=MovementType.RETURN_IN,reverses__isnull=True).order_by("id")
        if not movements.exists(): raise ValueError("La devolución no tiene historia.")
        for m in movements:
            StockMovementReversalService.reverse(movement=m,reversal_type=MovementType.RETURN_OUT,user=user)
        return DocumentService.cancel(ret,user)
