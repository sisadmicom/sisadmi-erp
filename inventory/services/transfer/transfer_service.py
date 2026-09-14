from inventory.services.transfer.transfer_confirmation_service import (
    TransferConfirmationService,
)

from inventory.services.transfer.transfer_cancellation_service import (
    TransferCancellationService,
)

class TransferService:

    @staticmethod
    def confirm(
        transfer_id,
        user=None,
    ):

        return TransferConfirmationService.confirm(
            transfer_id=transfer_id,
            user=user,
        )
    @staticmethod
    def cancel(
        transfer_id,
        user=None,
    ):

        return TransferCancellationService.cancel(
            transfer_id=transfer_id,
            user=user,
        )