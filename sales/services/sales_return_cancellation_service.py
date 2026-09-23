from django.db import transaction
from django.core.exceptions import ValidationError
from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from sales.models import SalesReturn
from sales.services.sales_return_history import validated_sales_return_movements


class SalesReturnCancellationService:
    @staticmethod
    @transaction.atomic
    def execute(sales_return_id, user=None):
        ret = SalesReturn.objects.select_for_update().get(pk=sales_return_id)
        DocumentService.ensure_can_cancel(ret)
        manifests = validated_sales_return_movements(ret, lock=True)
        for row in manifests:
            StockMovementReversalService.reverse(
                movement=row.stock_movement,
                reversal_type=MovementType.RETURN_OUT,
                user=user,
            )
        return DocumentService.cancel(ret, user)
