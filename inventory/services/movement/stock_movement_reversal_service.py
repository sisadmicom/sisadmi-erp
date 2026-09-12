from django.db import transaction

from core.exceptions.inventory import InventoryException
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.stock.decrease_stock import DecreaseStock
from inventory.services.stock.increase_stock import IncreaseStock


class StockMovementReversalService:
    """Compensa totalmente un movimiento usando su historia persistida."""

    @staticmethod
    @transaction.atomic
    def reverse(*, movement, reversal_type, user=None):
        # Serializa las reversiones del mismo original y descarta datos/cachés
        # de la instancia recibida antes de comprobar las compensaciones.
        original = StockMovement.objects.select_for_update().get(pk=movement.pk)

        if original.reverses_id is not None:
            raise InventoryException("No se puede revertir una reversión.")

        if original.reversal_movements.exists():
            raise InventoryException("El movimiento ya fue revertido.")

        original_is_input = MovementType.is_input(original.movement_type)
        original_is_output = MovementType.is_output(original.movement_type)
        reversal_is_input = MovementType.is_input(reversal_type)
        reversal_is_output = MovementType.is_output(reversal_type)

        if (
            original_is_input == original_is_output
            or reversal_is_input == reversal_is_output
        ):
            raise InventoryException("El tipo de movimiento no tiene una dirección válida.")

        if original_is_input == reversal_is_input:
            raise InventoryException("La reversión debe tener dirección contraria.")

        stock_service = IncreaseStock() if original_is_output else DecreaseStock()
        stock_service.execute(
            company=original.company,
            branch=original.branch,
            warehouse=original.warehouse,
            product=original.product,
            quantity=original.quantity,
            unit_cost=original.unit_cost,
            document=original.document,
            movement_type=reversal_type,
            reverses=original,
            user=user,
            notes=f"Reversión del movimiento {original.pk}",
        )

        return original.reversal_movements.get()
