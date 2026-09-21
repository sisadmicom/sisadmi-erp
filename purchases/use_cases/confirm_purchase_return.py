from purchases.services.purchase_return_confirmation_service import PurchaseReturnConfirmationService


class ConfirmPurchaseReturn:
    @staticmethod
    def execute(purchase_return_id, user=None):
        return PurchaseReturnConfirmationService.execute(purchase_return_id, user=user)
