from sales.services.sale_service import SaleService


class CancelSale:

    @staticmethod
    def execute(
        sale_id,
        user=None,
    ):

        return SaleService.cancel(
            sale_id=sale_id,
            user=user,
        )
