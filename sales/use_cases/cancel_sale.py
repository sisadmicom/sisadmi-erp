from django.db import transaction

from sales.services.sale_service import SaleService


class CancelSale:

    @staticmethod
    @transaction.atomic
    def execute(
        sale_id,
        user=None,
    ):

        return SaleService.cancel(
            sale_id=sale_id,
            user=user,
        )
