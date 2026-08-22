from django.db import transaction

from purchases.models import Purchase
from purchases.services.purchase_service import PurchaseService


class ConfirmPurchase:

    @staticmethod
    @transaction.atomic
    def execute(
        purchase_id: int,
        user,
    ):

        purchase = Purchase.objects.select_for_update().get(
            pk=purchase_id
        )

        return PurchaseService.confirm(
            purchase=purchase,
            user=user,
        )