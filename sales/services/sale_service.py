# sales/services/sale_service.py

from sales.services.sale_confirmation_service import (
    SaleConfirmationService,
)

from sales.services.sale_cancellation_service import (
    SaleCancellationService,
)


class SaleService:

    @staticmethod
    def confirm(
        sale_id,
        user=None,
    ):

        return SaleConfirmationService.confirm(
            sale_id=sale_id,
            user=user,
        )

    @staticmethod
    def cancel(
        sale_id,
        user=None,
    ):

        return SaleCancellationService.cancel(
            sale_id=sale_id,
            user=user,
        )