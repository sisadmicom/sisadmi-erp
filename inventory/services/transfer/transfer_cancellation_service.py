from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from core.exceptions.inventory import InventoryException
from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement, Transfer
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService


class TransferCancellationService:
    @staticmethod
    @transaction.atomic
    def cancel(transfer_id, user=None):
        transfer = Transfer.objects.select_for_update().get(pk=transfer_id)
        DocumentService.ensure_can_cancel(transfer)
        pairs = list(transfer.movement_pairs.select_for_update().select_related("out_movement", "in_movement").order_by("pk"))
        if not pairs:
            raise InventoryException("La transferencia no tiene manifiesto de inventario.")
        out_ids, in_ids = {p.out_movement_id for p in pairs}, {p.in_movement_id for p in pairs}
        if out_ids & in_ids:
            raise InventoryException("El manifiesto reutiliza movimientos entre OUT e IN.")
        expected = out_ids | in_ids
        ct = ContentType.objects.get_for_model(transfer)
        originals = list(StockMovement.objects.select_for_update(of=("self",)).filter(content_type=ct, object_id=transfer.pk, movement_type__in=(MovementType.TRANSFER_OUT, MovementType.TRANSFER_IN), reverses__isnull=True).order_by("pk"))
        if expected != {m.pk for m in originals}:
            raise InventoryException("El manifiesto no coincide con la historia de inventario.")
        for pair in pairs:
            out, inc = pair.out_movement, pair.in_movement
            if out.pk == inc.pk or out.pk in in_ids or inc.pk in out_ids:
                raise InventoryException("El par reutiliza movimientos.")
            if out.movement_type != MovementType.TRANSFER_OUT or inc.movement_type != MovementType.TRANSFER_IN:
                raise InventoryException("Tipo de movimiento incompatible con el manifiesto.")
            if out.document != transfer or inc.document != transfer:
                raise InventoryException("Documento incompatible con el manifiesto.")
            if out.reverses_id is not None or inc.reverses_id is not None or out.reversal_movements.exists() or inc.reversal_movements.exists():
                raise InventoryException("Movimiento original ya revertido.")
            if (out.product_id != inc.product_id or out.quantity != inc.quantity or out.warehouse_id == inc.warehouse_id or out.company_id != inc.company_id or out.branch_id != inc.branch_id or out.unit_cost != inc.unit_cost):
                raise InventoryException("Contexto del par inconsistente.")
        for pair in pairs:
            StockMovementReversalService.reverse(movement=pair.in_movement, reversal_type=MovementType.RETURN_OUT, user=user)
        for pair in pairs:
            StockMovementReversalService.reverse(movement=pair.out_movement, reversal_type=MovementType.RETURN_IN, user=user)
        return DocumentService.cancel(document=transfer, user=user)
