from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import Stock
from inventory.services.movement.create_stock_movement import (
    CreateStockMovement,
)


class DecreaseStock:
    """
    Disminuye el inventario de un producto.

    Toda salida de inventario debe:
    1. Validar existencia del stock.
    2. Bloquear el registro para evitar condiciones de carrera.
    3. Validar stock disponible.
    4. Disminuir la existencia.
    5. Registrar el movimiento.
    """

    @transaction.atomic
    def execute(
        self,
        *,
        company,
        branch,
        warehouse,
        product,
        quantity,
        movement_type,
        unit_cost=0,
        document=None,
        notes="",
        user=None,
    ):
        try:
            stock = Stock.objects.select_for_update().get(
                company=company,
                branch=branch,
                warehouse=warehouse,
                product=product,
            )
        except Stock.DoesNotExist:
            raise ValidationError(
                f"No existe inventario para {product}."
            )

        if quantity <= 0:
            raise ValidationError(
                "La cantidad debe ser mayor que cero."
            )

        if stock.available_quantity < quantity:
            raise ValidationError(
                "No existe stock suficiente."
            )

        stock.quantity -= quantity

        stock.save(
            update_fields=[
                "quantity",
                "updated_at",
            ]
        )

        CreateStockMovement().execute(
            company=company,
            branch=branch,
            warehouse=warehouse,
            product=product,
            movement_type=movement_type,
            quantity=quantity,
            unit_cost=unit_cost,
            document=document,
            notes=notes,
            user=user,
        )

        return stock