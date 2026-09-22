from django.db import transaction

from core.exceptions.inventory import InventoryException
from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.models import Warehouse
from inventory.services import IncreaseStock
from purchases.models import Purchase, PurchaseMovement
from purchases.validators.purchase_validator import PurchaseValidator


class PurchaseConfirmationService:
    @staticmethod
    @transaction.atomic
    def confirm(purchase_id, user=None):
        purchase = Purchase.objects.select_for_update().get(pk=purchase_id)
        DocumentService.ensure_can_confirm(purchase)
        PurchaseValidator.validate_confirmation(purchase)
        warehouses = list(Warehouse.objects.filter(
            company=purchase.company, branch=purchase.branch, is_main=True,
        ))
        if len(warehouses) != 1:
            raise InventoryException("La compra requiere exactamente una bodega principal.")
        warehouse = warehouses[0]
        purchase = DocumentService.confirm(document=purchase, user=user)
        increase = IncreaseStock()
        for detail in purchase.details.all():
            movement = increase.execute(
                company=purchase.company, branch=purchase.branch, warehouse=warehouse,
                product=detail.product, quantity=detail.quantity,
                movement_type=MovementType.PURCHASE, unit_cost=detail.unit_price,
                document=purchase, notes=f"Compra {purchase.number}", user=user,
                return_movement=True,
            )
            PurchaseMovement.objects.create(purchase=purchase, stock_movement=movement)
        return purchase
