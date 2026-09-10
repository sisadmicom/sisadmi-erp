from django.db import transaction

from core.services.document_service import DocumentService

from inventory.constants.movement_type import MovementType
from inventory.services.stock.decrease_stock import DecreaseStock
from inventory.services.stock.increase_stock import IncreaseStock

from inventory.validators.transfer_validator import TransferValidator


class TransferCancellationService:

    @staticmethod
    @transaction.atomic
    def cancel(
        transfer,
        user=None,
    ):

        DocumentService.ensure_can_cancel(transfer)

        TransferValidator.validate_cancellation(
            transfer
        )

        increase = IncreaseStock()
        decrease = DecreaseStock()

        for detail in transfer.details.all():

            # Devolver la cantidad a la bodega origen.
            increase.execute(
                company=transfer.company,
                branch=transfer.branch,
                warehouse=transfer.source_warehouse,
                product=detail.product,
                quantity=detail.quantity,
                movement_type=MovementType.RETURN_IN,
                document=transfer,
                notes=f"Anulación transferencia {transfer.number}",
                user=user,
            )

            # Retirar la cantidad que había ingresado
            # a la bodega destino.
            decrease.execute(
                company=transfer.company,
                branch=transfer.branch,
                warehouse=transfer.destination_warehouse,
                product=detail.product,
                quantity=detail.quantity,
                movement_type=MovementType.RETURN_OUT,
                document=transfer,
                notes=f"Anulación transferencia {transfer.number}",
                user=user,
            )

        return DocumentService.cancel(
            document=transfer,
            user=user,
        )
