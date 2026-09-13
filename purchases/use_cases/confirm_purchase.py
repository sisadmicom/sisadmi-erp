from purchases.services.purchase_service import PurchaseService


class ConfirmPurchase:

    @staticmethod
    def execute(
        purchase_id: int,
        user,
    ):
        return PurchaseService.confirm(
            purchase_id=purchase_id,
            user=user,
        )
