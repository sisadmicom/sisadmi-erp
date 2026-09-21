from purchases.services.purchase_return_creator import PurchaseReturnCreator


class CreatePurchaseReturn:
    @staticmethod
    def execute(dto):
        return PurchaseReturnCreator.execute(dto)
