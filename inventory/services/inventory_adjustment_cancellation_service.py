from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from core.exceptions.inventory import InventoryException
from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.models import (
    InventoryAdjustment,
    InventoryAdjustmentMovement,
    Stock,
    StockMovement,
)
from inventory.services.movement.stock_movement_reversal_service import (
    StockMovementReversalService,
)


class InventoryAdjustmentCancellationService:
    @staticmethod
    @transaction.atomic
    def cancel(adjustment_id, user=None):
        adjustment = InventoryAdjustment.objects.select_for_update().get(pk=adjustment_id)
        DocumentService.ensure_can_cancel(adjustment)

        manifest_rows = list(
            InventoryAdjustmentMovement.objects.select_for_update()
            .filter(inventory_adjustment=adjustment)
            .order_by("pk")
        )
        expected_ids = {row.stock_movement_id for row in manifest_rows}
        if not expected_ids:
            raise InventoryException("El ajuste no tiene manifiesto de historia de inventario.")

        content_type = ContentType.objects.get_for_model(InventoryAdjustment)
        originals = list(
            StockMovement.objects.select_for_update()
            .filter(
                content_type=content_type,
                object_id=adjustment.pk,
                movement_type__in=(
                    MovementType.ADJUSTMENT_IN,
                    MovementType.ADJUSTMENT_OUT,
                ),
                reverses__isnull=True,
            )
            .order_by("pk")
        )
        actual_ids = {movement.pk for movement in originals}
        if expected_ids != actual_ids:
            raise InventoryException("El manifiesto y la historia del ajuste no coinciden.")

        if any(row.inventory_adjustment_id != adjustment.pk for row in manifest_rows):
            raise InventoryException("El manifiesto del ajuste es inconsistente.")

        movement_types = {movement.movement_type for movement in originals}
        if len(movement_types) != 1:
            raise InventoryException("La historia del ajuste mezcla direcciones.")

        stock_by_key = {}
        for movement in originals:
            if movement.content_type_id != content_type.pk or movement.object_id != adjustment.pk:
                raise InventoryException("El movimiento no pertenece al ajuste.")
            if movement.movement_type not in (
                MovementType.ADJUSTMENT_IN,
                MovementType.ADJUSTMENT_OUT,
            ):
                raise InventoryException("La historia del ajuste tiene un tipo inválido.")
            if movement.company_id != adjustment.company_id:
                raise InventoryException("La historia del ajuste tiene una empresa inválida.")
            if movement.branch_id != adjustment.branch_id:
                raise InventoryException("La historia del ajuste tiene una sucursal inválida.")
            if movement.reverses_id is not None:
                raise InventoryException("El movimiento original no puede ser una reversión.")
            if movement.reversal_movements.exists():
                raise InventoryException("El movimiento del ajuste ya fue revertido.")
            if movement.quantity <= 0:
                raise InventoryException("La cantidad histórica del ajuste es inválida.")

            key = (movement.company_id, movement.branch_id, movement.warehouse_id, movement.product_id)
            stock_by_key[key] = Stock.objects.select_for_update().filter(
                company_id=movement.company_id,
                branch_id=movement.branch_id,
                warehouse_id=movement.warehouse_id,
                product_id=movement.product_id,
            ).first()
            if movement.movement_type == MovementType.ADJUSTMENT_IN:
                stock = stock_by_key[key]
                if stock is None or stock.available_quantity < movement.quantity:
                    raise InventoryException("No existe stock suficiente para revertir el ajuste.")

        for movement in originals:
            reversal_type = (
                MovementType.RETURN_OUT
                if movement.movement_type == MovementType.ADJUSTMENT_IN
                else MovementType.RETURN_IN
            )
            StockMovementReversalService.reverse(
                movement=movement,
                reversal_type=reversal_type,
                user=user,
            )

        return DocumentService.cancel(adjustment, user=user)
