from django.db import transaction

from core.services.document_service import DocumentService

from inventory.models import Warehouse
from inventory.constants.movement_type import MovementType
from inventory.services import IncreaseStock

from purchases.validators.purchase_validator import PurchaseValidator


class PurchaseConfirmationService:

    @staticmethod
    @transaction.atomic
    def confirm(
        purchase,
        user=None,
    ):

        PurchaseValidator.validate_confirmation(
            purchase
        )

        warehouse = Warehouse.objects.get(
            company=purchase.company,
            branch=purchase.branch,
            is_main=True,
        )

        # PRIMERO confirmar el documento para obtener el número definitivo
        purchase = DocumentService.confirm(
            document=purchase,
            user=user,
        )

        increase = IncreaseStock()

        for detail in purchase.details.all():

            increase.execute(
                company=purchase.company,
                branch=purchase.branch,
                warehouse=warehouse,
                product=detail.product,
                quantity=detail.quantity,
                movement_type=MovementType.PURCHASE,
                unit_cost=detail.unit_price,
                document=purchase,
                notes=f"Compra {purchase.number}",
                user=user,
            )

        return purchase