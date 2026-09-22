from django.contrib.contenttypes.models import ContentType

from core.exceptions.inventory import InventoryException
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from sales.models import SaleMovement


def validated_sale_movements(sale, *, lock=False):
    """Return the exact original SALE movements recorded for ``sale``."""
    manifests = SaleMovement.objects.filter(sale=sale).order_by("pk")
    if lock:
        manifests = manifests.select_for_update()
    manifests = list(manifests.select_related("stock_movement"))
    if not manifests:
        raise InventoryException("La venta no tiene manifiesto de inventario.")

    content_type = ContentType.objects.get_for_model(sale)
    originals_qs = StockMovement.objects.filter(
        content_type=content_type,
        object_id=sale.pk,
        movement_type=MovementType.SALE,
        reverses__isnull=True,
    ).order_by("pk")
    if lock:
        originals_qs = originals_qs.select_for_update()
    originals = list(originals_qs)
    expected_ids = {row.stock_movement_id for row in manifests}
    actual_ids = {row.pk for row in originals}
    if expected_ids != actual_ids:
        raise InventoryException("El manifiesto no coincide con la historia SALE.")

    for row in manifests:
        movement = row.stock_movement
        if (
            movement.movement_type != MovementType.SALE
            or movement.content_type_id != content_type.pk
            or movement.object_id != sale.pk
            or movement.company_id != sale.company_id
            or movement.branch_id != sale.branch_id
            or movement.reverses_id is not None
            or movement.reversal_movements.exists()
        ):
            raise InventoryException("Movimiento SALE manifestado incompatible.")
    return [row.stock_movement for row in manifests]
