from inventory.services.transfer import TransferService


class CancelTransfer:

    @staticmethod
    def execute(
        transfer_id,
        user=None,
    ):

        return TransferService.cancel(
            transfer_id=transfer_id,
            user=user,
        )
