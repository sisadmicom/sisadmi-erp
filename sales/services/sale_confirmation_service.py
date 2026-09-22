from django.db import transaction

from core.services.document_service import DocumentService

from inventory.constants.movement_type import MovementType
from inventory.services.stock.decrease_stock import DecreaseStock

from sales.models import Sale, SaleMovement
from sales.services.sale_validator import SaleValidator


class SaleConfirmationService:

    @staticmethod
    @transaction.atomic
    def confirm(
        sale_id,
        user,
    ):

        sale = Sale.objects.select_for_update().get(pk=sale_id)

        DocumentService.ensure_can_confirm(sale)
        SaleValidator.validate_confirmation(sale)

        DocumentService.confirm(
            document=sale,
            user=user,
        )

        decrease_stock = DecreaseStock()

        for detail in sale.details.all():

            movement = decrease_stock.execute(

                company=sale.company,
                branch=sale.branch,
                warehouse=sale.warehouse,

                product=detail.product,
                quantity=detail.quantity,

                movement_type=MovementType.SALE,

                document=sale,

                notes=f"Venta {sale.number}",

                user=user,
                return_movement=True,
            )
            SaleMovement.objects.create(sale=sale, stock_movement=movement)

        return sale