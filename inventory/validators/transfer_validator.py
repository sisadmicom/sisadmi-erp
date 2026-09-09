from core.validators.document_detail_validator import DocumentDetailValidator
from core.validators.quantity_line_validator import QuantityLineValidator

from inventory.models import Warehouse


class TransferValidator:

    @staticmethod
    def validate(dto):

        DocumentDetailValidator.validate_required(bool(dto.details))

        if dto.source_warehouse_id == dto.destination_warehouse_id:
            raise ValueError(
                "La bodega origen y destino no pueden ser la misma."
            )

        product_ids = set()

        for detail in dto.details:

            QuantityLineValidator.validate(detail)

            if detail.product_id in product_ids:
                raise ValueError(
                    "No se puede repetir un producto "
                    "en una transferencia."
                )

            product_ids.add(detail.product_id)

        source = Warehouse.objects.get(
            pk=dto.source_warehouse_id
        )

        destination = Warehouse.objects.get(
            pk=dto.destination_warehouse_id
        )

        if source.company_id != dto.company_id:
            raise ValueError(
                "La bodega origen no pertenece a la empresa."
            )

        if destination.company_id != dto.company_id:
            raise ValueError(
                "La bodega destino no pertenece a la empresa."
            )

        if source.branch_id != dto.branch_id:
            raise ValueError(
                "La bodega origen no pertenece a la sucursal."
            )

        if destination.branch_id != dto.branch_id:
            raise ValueError(
                "La bodega destino no pertenece a la sucursal."
            )

    @staticmethod
    def validate_confirmation(transfer):

        if not transfer.is_draft():
            raise ValueError(
                "La transferencia no está en borrador."
            )

        if (
            transfer.source_warehouse_id
            == transfer.destination_warehouse_id
        ):
            raise ValueError(
                "La bodega origen y destino no pueden ser la misma."
            )

        details = transfer.details.all()

        DocumentDetailValidator.validate_required(details.exists())

        product_ids = set()

        for detail in details:

            QuantityLineValidator.validate(detail)

            if detail.product_id in product_ids:
                raise ValueError(
                    "No se puede repetir un producto "
                    "en una transferencia."
                )

            product_ids.add(detail.product_id)

    @staticmethod
    def validate_cancellation(transfer):

        if transfer.is_cancelled():
            raise ValueError(
                "La transferencia ya fue anulada."
            )

        if not transfer.is_confirmed():
            raise ValueError(
                "Solo se pueden anular transferencias confirmadas."
            )

        details = transfer.details.all()

        if not details.exists():
            raise ValueError(
                "La transferencia no tiene detalles."
            )