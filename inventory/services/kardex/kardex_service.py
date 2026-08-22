from decimal import Decimal

from inventory.dto import KardexRow
from inventory.models import StockMovement

from inventory.constants.movement_type import MovementType


class KardexService:
    """
    Reconstruye el Kardex a partir del historial
    de movimientos.
    """

    @staticmethod
    def get_kardex(
        *,
        company,
        branch,
        warehouse,
        product,
        from_date=None,
        to_date=None,
    ):
        movements = (
            StockMovement.objects
            .filter(
                company=company,
                branch=branch,
                warehouse=warehouse,
                product=product,
            )
            .select_related(
                "product",
                "warehouse",
                "content_type",
            )
            .order_by(
                "movement_date",
                "id",
            )
        )

        if from_date:
            movements = movements.filter(
                movement_date__gte=from_date
            )

        if to_date:
            movements = movements.filter(
                movement_date__lte=to_date
            )

        balance = Decimal("0")
        rows = []

        for movement in movements:

            if MovementType.is_input(
                movement.movement_type
            ):
                quantity_in = movement.quantity
                quantity_out = Decimal("0")
                balance += movement.quantity

            elif MovementType.is_output(
                movement.movement_type
            ):
                quantity_in = Decimal("0")
                quantity_out = movement.quantity
                balance -= movement.quantity

            else:
                raise ValueError(
                    f"Tipo de movimiento no soportado: "
                    f"{movement.movement_type}"
                )

            document = movement.document

            document_number = None
            document_type = None

            if document:
                document_number = getattr(
                    document,
                    "number",
                    None,
                )

                document_type = (
                    document.__class__.__name__
                )

            rows.append(
                KardexRow(
                    movement_date=movement.movement_date,
                    movement_type=(
                        movement.get_movement_type_display()
                    ),
                    document=(
                        str(document)
                        if document
                        else None
                    ),
                    document_number=document_number,
                    document_type=document_type,
                    warehouse_name=movement.warehouse.name,
                    quantity_in=quantity_in,
                    quantity_out=quantity_out,
                    balance=balance,
                    notes=movement.notes,
                )
            )

        return rows

    @staticmethod
    def get_product(
        *,
        company,
        branch,
        warehouse,
        product,
        from_date=None,
        to_date=None,
    ):
        """
        Obtiene el Kardex de un producto.

        Mantiene una interfaz simple para consultar
        el Kardex de un producto dentro de una bodega.
        """

        return KardexService.get_kardex(
            company=company,
            branch=branch,
            warehouse=warehouse,
            product=product,
            from_date=from_date,
            to_date=to_date,
        )