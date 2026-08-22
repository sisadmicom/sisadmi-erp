from django.db import transaction

from purchases.models import Purchase
from purchases.services.purchase_service import PurchaseService


class CancelPurchase:

    @staticmethod
    @transaction.atomic
    def execute(
        purchase_id: int,
        user=None,
    ):

        purchase = (
            Purchase.objects
            .select_for_update()
            .prefetch_related(
                "details__product",
            )
            .get(pk=purchase_id)
        )

        return PurchaseService.cancel(
            purchase=purchase,
            user=user,
        )