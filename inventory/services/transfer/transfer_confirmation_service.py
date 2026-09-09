from django.db import transaction

from core.services.document_service import DocumentService

from inventory.constants.movement_type import MovementType
from inventory.services.stock.decrease_stock import DecreaseStock
from inventory.services.stock.increase_stock import IncreaseStock

from inventory.validators.transfer_validator import TransferValidator


class TransferConfirmationService:

    @staticmethod
    @transaction.atomic
    def confirm(
        transfer,
        user=None,
    ):

        DocumentService.ensure_can_confirm(transfer)
        TransferValidator.validate_confirmation(
            transfer
        )

        # Primero confirmamos el documento para obtener
        # el número oficial de la transferencia.
        transfer = DocumentService.confirm(
            document=transfer,
            user=user,
        )

        decrease_stock = DecreaseStock()
        increase_stock = IncreaseStock()

        # Salida de la bodega origen.
        for detail in transfer.details.all():

            decrease_stock.execute(
                company=transfer.company,
                branch=transfer.branch,
                warehouse=transfer.source_warehouse,
                product=detail.product,
                quantity=detail.quantity,
                movement_type=MovementType.TRANSFER_OUT,
                document=transfer,
                notes=f"Transferencia salida {transfer.number}",
                user=user,
            )

        # Entrada en la bodega destino.
        for detail in transfer.details.all():

            increase_stock.execute(
                company=transfer.company,
                branch=transfer.branch,
                warehouse=transfer.destination_warehouse,
                product=detail.product,
                quantity=detail.quantity,
                movement_type=MovementType.TRANSFER_IN,
                document=transfer,
                notes=f"Transferencia entrada {transfer.number}",
                user=user,
            )

        return transfer