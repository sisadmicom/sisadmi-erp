from django.db import transaction

from inventory.constants.movement_type import MovementType
from inventory.services.stock import IncreaseStock


class InventoryReceiptService:

    @staticmethod
    @transaction.atomic
    def receive_purchase(
        *,
        purchase,
        user=None,
    ):
        """
        Recibe una compra e incrementa el stock de todos sus productos.
        """

        increase = IncreaseStock()

        for detail in purchase.details.all():

            increase.execute(
                company=purchase.company,
                branch=purchase.branch,
                warehouse=purchase.warehouse,
                product=detail.product,
                quantity=detail.quantity,
                movement_type=MovementType.PURCHASE,
                document=purchase,
                notes=f"Compra {purchase.number or purchase.id}",
                user=user,
            )

        return purchase