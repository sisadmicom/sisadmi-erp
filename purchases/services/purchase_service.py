# purchases/services/purchase_service.py

from django.db import transaction

from purchases.models import Purchase

from core.services.document_totals_service import (
    DocumentTotalsService,
)

from purchases.services.purchase_confirmation_service import (
    PurchaseConfirmationService,
)

from purchases.use_cases.create_purchase import CreatePurchase

from purchases.services.purchase_cancellation_service import (
    PurchaseCancellationService,
)

class PurchaseService:
    """
    Servicio principal del módulo de Compras.
    """

    @staticmethod
    @transaction.atomic
    def create(dto):
        return CreatePurchase.execute(dto)

    @staticmethod
    @transaction.atomic
    def calculate(purchase):
        """
        Recalcula los totales del documento.
        """
        return DocumentTotalsService.calculate(purchase)

    @staticmethod
    @transaction.atomic
    def confirm(
        purchase,
        user
    ):
        """
        Confirma una compra.
        """
        return PurchaseConfirmationService.confirm(
            purchase=purchase,
            user=user,
        )

    @staticmethod
    @transaction.atomic
    def cancel(
        purchase,
        user=None,
    ):
        return PurchaseCancellationService.cancel(
            purchase=purchase,
            user=user,
        )

    @staticmethod
    @transaction.atomic
    def close(
        purchase,
        user
    ):
        """
        Cierra una compra.
        """
        raise NotImplementedError(
            "Cierre aún no implementado."
        )