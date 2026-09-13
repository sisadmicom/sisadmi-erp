from purchases.services.purchase_service import PurchaseService


class CancelPurchase:

    @staticmethod
    def execute(
        purchase_id: int,
        user=None,
    ):
        return PurchaseService.cancel(
            purchase_id=purchase_id,
            user=user,
        )
