from inventory.services.transfer import TransferService


class ConfirmTransfer:

    @staticmethod
    def execute(
        transfer_id,
        user=None,
    ):

        return TransferService.confirm(
            transfer_id=transfer_id,
            user=user,
        )
