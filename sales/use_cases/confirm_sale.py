from sales.services.sale_service import SaleService

class ConfirmSale:

    @staticmethod
    def execute(
        sale_id,
        user=None,
    ):
        return SaleService.confirm(
            sale_id=sale_id,
            user=user,
        )