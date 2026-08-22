# sales/services/sale_service.py

from django.db import transaction

from sales.models import Sale

from sales.services.sale_confirmation_service import (
    SaleConfirmationService,
)

from sales.services.sale_cancellation_service import (
    SaleCancellationService,
)


class SaleService:

    @staticmethod
    @transaction.atomic
    def confirm(
        sale_id,
        user=None,
    ):

        sale = (
            Sale.objects
            .select_related(
                "company",
                "branch",
                "warehouse",
                "customer",
            )
            .prefetch_related(
                "details__product",
            )
            .get(pk=sale_id)
        )

        return SaleConfirmationService.confirm(
            sale=sale,
            user=user,
        )

    @staticmethod
    @transaction.atomic
    def cancel(
        sale_id,
        user=None,
    ):

        sale = (
            Sale.objects
            .select_related(
                "company",
                "branch",
                "warehouse",
                "customer",
            )
            .prefetch_related(
                "details__product",
            )
            .get(pk=sale_id)
        )

        return SaleCancellationService.cancel(
            sale=sale,
            user=user,
        )