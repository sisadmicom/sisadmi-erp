from django.db import transaction

from inventory.services.transfer import TransferService


class CancelTransfer:

    @staticmethod
    @transaction.atomic
    def execute(
        transfer_id,
        user=None,
    ):

        return TransferService.cancel(
            transfer_id=transfer_id,
            user=user,
        )
