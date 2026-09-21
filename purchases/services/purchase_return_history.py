from collections import defaultdict
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from core.validators.operational_context_validator import OperationalContextValidator
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement


def purchase_history(purchase):
    """Bodega y costos inequívocos, exclusivamente desde la recepción histórica."""
    OperationalContextValidator.validate_company_branch(purchase.company, purchase.branch)
    details = list(purchase.details.select_related("product"))
    movements = list(StockMovement.objects.filter(
        content_type=ContentType.objects.get_for_model(purchase), object_id=purchase.pk,
        movement_type=MovementType.PURCHASE, reverses__isnull=True,
    ).select_related("warehouse", "product"))
    if not movements or len({row.warehouse_id for row in movements}) != 1:
        raise ValidationError("La compra requiere una bodega histórica inequívoca.")

    received = defaultdict(lambda: Decimal("0"))
    purchased = defaultdict(lambda: Decimal("0"))
    costs = defaultdict(set)
    for row in movements:
        if (row.company_id, row.branch_id) != (purchase.company_id, purchase.branch_id):
            raise ValidationError("Contexto del movimiento PURCHASE inconsistente.")
        OperationalContextValidator.validate_inventory(
            purchase.company, purchase.branch, row.warehouse, row.product,
        )
        if row.quantity <= 0 or row.reversal_movements.exists():
            raise ValidationError("Historia PURCHASE inválida o revertida.")
        received[row.product_id] += row.quantity
        costs[row.product_id].add(row.unit_cost)
    for detail in details:
        OperationalContextValidator.validate_product(purchase.company, detail.product)
        if detail.quantity <= 0:
            raise ValidationError("Cantidad histórica de compra inválida.")
        purchased[detail.product_id] += detail.quantity
    if dict(received) != dict(purchased):
        raise ValidationError("Los productos y cantidades no coinciden con la historia PURCHASE.")
    if any(len(values) != 1 for values in costs.values()):
        raise ValidationError("Costo histórico ambiguo para el producto de la compra.")
    # Todas las filas tienen la misma bodega y un único costo por producto;
    # no se asigna una línea a un movimiento por orden de PK.
    warehouse = movements[0].warehouse
    return warehouse, {product_id: next(iter(values)) for product_id, values in costs.items()}
