from django.db import transaction

from inventory.services.transfer import TransferService


class ConfirmTransfer:

    @staticmethod
    @transaction.atomic
    def execute(
        transfer_id,
        user=None,
    ):

        return TransferService.confirm(
            transfer_id=transfer_id,
            user=user,
        )
