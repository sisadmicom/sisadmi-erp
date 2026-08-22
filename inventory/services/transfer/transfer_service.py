from django.db import transaction

from inventory.models import Transfer

from inventory.services.transfer.transfer_confirmation_service import (
    TransferConfirmationService,
)

from inventory.services.transfer.transfer_cancellation_service import (
    TransferCancellationService,
)

class TransferService:

    @staticmethod
    @transaction.atomic
    def confirm(
        transfer_id,
        user=None,
    ):

        transfer = (
            Transfer.objects
            .select_related(
                "company",
                "branch",
                "source_warehouse",
                "destination_warehouse",
            )
            .prefetch_related(
                "details__product",
            )
            .get(pk=transfer_id)
        )

        return TransferConfirmationService.confirm(
            transfer=transfer,
            user=user,
        )
    @staticmethod
    @transaction.atomic
    def cancel(
        transfer_id,
        user=None,
    ):

        transfer = (
            Transfer.objects
            .select_related(
                "company",
                "branch",
                "source_warehouse",
                "destination_warehouse",
            )
            .prefetch_related(
                "details__product",
            )
            .get(pk=transfer_id)
        )

        return TransferCancellationService.cancel(
            transfer=transfer,
            user=user,
        )