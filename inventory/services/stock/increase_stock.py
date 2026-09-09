from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import Stock
from inventory.services.movement import CreateStockMovement


class IncreaseStock:

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

        if quantity <= 0:
            raise ValidationError(
                "La cantidad debe ser mayor que cero."
            )

        stock, _ = Stock.objects.select_for_update().get_or_create(
            company=company,
            branch=branch,
            warehouse=warehouse,
            product=product,
            defaults={
                "quantity": 0,
                "reserved_quantity": 0,
            },
        )

        stock.quantity += quantity

        stock.save(
            update_fields=["quantity"]
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