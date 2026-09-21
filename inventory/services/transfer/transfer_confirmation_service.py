from django.db import transaction

from core.exceptions.inventory import InventoryException
from core.services.document_service import DocumentService

from inventory.constants.movement_type import MovementType
from inventory.models import Transfer, TransferMovementPair
from inventory.services.stock.decrease_stock import DecreaseStock
from inventory.services.stock.increase_stock import IncreaseStock
from inventory.validators.transfer_validator import TransferValidator


class TransferConfirmationService:
    @staticmethod
    @transaction.atomic
    def confirm(transfer_id, user=None):
        transfer = Transfer.objects.select_for_update().get(pk=transfer_id)
        DocumentService.ensure_can_confirm(transfer)
        TransferValidator.validate_confirmation(transfer)
        if transfer.movement_pairs.exists():
            raise InventoryException("La transferencia ya tiene manifiesto operacional.")
        transfer = DocumentService.confirm(document=transfer, user=user)
        decrease_stock, increase_stock, used = DecreaseStock(), IncreaseStock(), set()
        for detail in transfer.details.all():
            out = decrease_stock.execute(company=transfer.company, branch=transfer.branch, warehouse=transfer.source_warehouse, product=detail.product, quantity=detail.quantity, movement_type=MovementType.TRANSFER_OUT, document=transfer, notes=f"Transferencia salida {transfer.number}", user=user, return_movement=True)
            incoming = increase_stock.execute(company=transfer.company, branch=transfer.branch, warehouse=transfer.destination_warehouse, product=detail.product, quantity=detail.quantity, movement_type=MovementType.TRANSFER_IN, document=transfer, notes=f"Transferencia entrada {transfer.number}", user=user, return_movement=True)
            TransferConfirmationService.validate_pair(transfer, out, incoming, used)
            TransferMovementPair.objects.create(transfer=transfer, out_movement=out, in_movement=incoming)
            used.update((out.pk, incoming.pk))
        return transfer

    @staticmethod
    def validate_pair(transfer, out, incoming, used=()):
        if out.pk == incoming.pk or out.pk in used or incoming.pk in used:
            raise InventoryException("Movimiento reutilizado en el manifiesto de transferencia.")
        if out.movement_type != MovementType.TRANSFER_OUT or out.document != transfer:
            raise InventoryException("TRANSFER_OUT inválido para la transferencia.")
        if incoming.movement_type != MovementType.TRANSFER_IN or incoming.document != transfer:
            raise InventoryException("TRANSFER_IN inválido para la transferencia.")
        if (out.product_id != incoming.product_id or out.quantity != incoming.quantity or out.warehouse_id == incoming.warehouse_id or out.company_id != incoming.company_id or out.branch_id != incoming.branch_id or out.unit_cost != incoming.unit_cost):
            raise InventoryException("El par de movimientos de transferencia es inconsistente.")
