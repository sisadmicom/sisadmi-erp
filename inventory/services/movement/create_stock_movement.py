from django.db import transaction

from inventory.models import StockMovement
from core.validators.operational_context_validator import OperationalContextValidator


class CreateStockMovement:

    @transaction.atomic
    def execute(
        self,
        *,
        company,
        branch,
        warehouse,
        product,
        movement_type,
        quantity,
        unit_cost=0,
        document=None,
        notes="",
        user=None,
        reverses=None,
    ):

        OperationalContextValidator.validate_inventory(company, branch, warehouse, product)

        movement = StockMovement(
            company=company,
            branch=branch,
            warehouse=warehouse,
            product=product,
            movement_type=movement_type,
            quantity=quantity,
            unit_cost=unit_cost,
            notes=notes,
            reverses=reverses,
        )

        if document is not None:
            movement.document = document

        movement.created_by = user

        movement.save()

        return movement