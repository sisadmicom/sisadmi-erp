from django.db import transaction

from core.services.document_service import DocumentService

from inventory.constants.movement_type import MovementType
from inventory.models import Warehouse
from inventory.services.stock.decrease_stock import DecreaseStock

from purchases.validators.purchase_validator import PurchaseValidator


class PurchaseCancellationService:

    @staticmethod
    @transaction.atomic
    def cancel(
        purchase,
        user=None,
    ):

        PurchaseValidator.validate_cancellation(
            purchase
        )

        warehouse = Warehouse.objects.get(
            company=purchase.company,
            branch=purchase.branch,
            is_main=True,
        )

        # Primero anulamos el documento.
        # La compra ya está confirmada y por tanto
        # conserva su número definitivo.
        purchase = DocumentService.cancel(
            document=purchase,
            user=user,
        )

        decrease = DecreaseStock()

        for detail in purchase.details.all():

            decrease.execute(
                company=purchase.company,
                branch=purchase.branch,
                warehouse=warehouse,
                product=detail.product,
                quantity=detail.quantity,
                movement_type=MovementType.RETURN_OUT,
                unit_cost=detail.unit_price,
                document=purchase,
                notes=f"Anulación compra {purchase.number}",
                user=user,
            )

        return purchase