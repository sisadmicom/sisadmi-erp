from purchases.services.purchase_return_cancellation_service import PurchaseReturnCancellationService


class CancelPurchaseReturn:
    @staticmethod
    def execute(purchase_return_id, user=None):
        return PurchaseReturnCancellationService.execute(purchase_return_id, user=user)
