from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from sales.models import SalesReturnMovement


def validated_sales_return_movements(sales_return, lock=False):
    """Validate exact membership and context of a SalesReturn's RETURN_IN effects."""
    manifests = SalesReturnMovement.objects.filter(
        sales_return=sales_return,
    ).select_related("stock_movement")
    if lock:
        manifests = manifests.select_for_update()
    manifests = list(manifests)
    expected_ids = {row.stock_movement_id for row in manifests}

    actual_qs = StockMovement.objects.filter(
        content_type=ContentType.objects.get_for_model(sales_return),
        object_id=sales_return.pk,
        movement_type=MovementType.RETURN_IN,
        reverses__isnull=True,
    )
    if lock:
        actual_qs = actual_qs.select_for_update()
    actual = list(actual_qs)
    actual_ids = {movement.pk for movement in actual}
    if expected_ids != actual_ids:
        raise ValidationError("La historia de devolución no coincide con sus efectos RETURN_IN.")

    for row in manifests:
        movement = row.stock_movement
        if movement.movement_type != MovementType.RETURN_IN:
            raise ValidationError("El manifest contiene un movimiento que no es RETURN_IN.")
        if movement.content_type_id != ContentType.objects.get_for_model(sales_return).pk or movement.object_id != sales_return.pk:
            raise ValidationError("El manifest contiene un movimiento de otro documento.")
        if movement.company_id != sales_return.company_id:
            raise ValidationError("La compañía del movimiento no coincide con la devolución.")
        if movement.branch_id != sales_return.branch_id:
            raise ValidationError("La sucursal del movimiento no coincide con la devolución.")
        if movement.reverses_id is not None:
            raise ValidationError("El movimiento manifestado ya es un reversal.")
        if StockMovement.objects.filter(reverses_id=movement.pk).exists():
            raise ValidationError("El movimiento RETURN_IN ya fue revertido.")
    return manifests
