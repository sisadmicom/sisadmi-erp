from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from purchases.models import Purchase, PurchaseMovement, PurchaseReturn
from core.constants.document_status import DocumentStatus
from core.exceptions.inventory import InventoryException
from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService


class PurchaseCancellationService:
    @staticmethod
    @transaction.atomic
    def cancel(purchase_id, user=None):
        purchase = Purchase.objects.select_for_update().get(pk=purchase_id)
        DocumentService.ensure_can_cancel(purchase)
        if PurchaseReturn.objects.filter(purchase=purchase, status=DocumentStatus.CONFIRMED).exists():
            raise InventoryException("La compra tiene devoluciones confirmadas.")
        manifests = list(PurchaseMovement.objects.select_for_update().select_related("stock_movement").filter(purchase=purchase).order_by("pk"))
        if not manifests:
            raise InventoryException("La compra no tiene manifiesto de inventario.")
        expected_ids = {row.stock_movement_id for row in manifests}
        content_type = ContentType.objects.get_for_model(purchase)
        originals = list(StockMovement.objects.select_for_update(of=("self",)).filter(
            content_type=content_type, object_id=purchase.pk,
            movement_type=MovementType.PURCHASE, reverses__isnull=True,
        ).order_by("pk"))
        if expected_ids != {row.pk for row in originals}:
            raise InventoryException("El manifiesto no coincide con la historia PURCHASE.")
        for row in manifests:
            movement = row.stock_movement
            if (movement.movement_type != MovementType.PURCHASE
                    or movement.content_type_id != content_type.pk
                    or movement.object_id != purchase.pk
                    or movement.company_id != purchase.company_id
                    or movement.branch_id != purchase.branch_id
                    or movement.reverses_id is not None
                    or movement.reversal_movements.exists()):
                raise InventoryException("Movimiento PURCHASE manifestado incompatible.")
        for row in manifests:
            StockMovementReversalService.reverse(
                movement=row.stock_movement, reversal_type=MovementType.RETURN_OUT, user=user,
            )
        return DocumentService.cancel(document=purchase, user=user)
