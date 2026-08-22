from django.db import transaction

from inventory.services.transfer import (
    TransferCreator,
)


class CreateTransfer:

    @staticmethod
    @transaction.atomic
    def execute(dto):

        return TransferCreator.create(dto)
