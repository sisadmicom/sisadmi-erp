# purchases/use_cases/create_purchase.py

from django.db import transaction

from purchases.services.purchase_creator import (
    PurchaseCreator,
)


class CreatePurchase:

    @staticmethod
    @transaction.atomic
    def execute(dto):

        return PurchaseCreator.create(
            dto
        )