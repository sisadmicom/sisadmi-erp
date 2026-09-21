from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction

from core.services.document_service import DocumentService
from core.validators.operational_context_validator import OperationalContextValidator
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.movement.stock_movement_reversal_service import StockMovementReversalService
from purchases.models import Purchase, PurchaseReturn
from purchases.validators.purchase_return_validator import PurchaseReturnValidator


class PurchaseReturnCancellationService:
    @staticmethod
    @transaction.atomic
    def execute(purchase_return_id, user=None):
        # Mismo orden que confirmación y CancelPurchase: Purchase antes de Return.
        purchase_id = PurchaseReturn.objects.values_list("purchase_id", flat=True).get(pk=purchase_return_id)
        purchase = Purchase.objects.select_for_update().get(pk=purchase_id)
        document = PurchaseReturn.objects.select_for_update().get(pk=purchase_return_id)
        DocumentService.ensure_can_cancel(document)
        PurchaseReturnValidator.validate_context(document, purchase)

        expected_ids = set(document.movement_manifest.select_for_update().values_list(
            "stock_movement_id", flat=True,
        ))
        content_type = ContentType.objects.get_for_model(document)
        actual_ids = set(StockMovement.objects.filter(
            content_type=content_type, object_id=document.pk,
            movement_type=MovementType.RETURN_OUT, reverses__isnull=True,
        ).values_list("pk", flat=True))
        if not expected_ids or expected_ids != actual_ids:
            raise ValidationError("El manifiesto no coincide con las salidas originales.")

        originals = list(StockMovement.objects.select_for_update(of=("self",)).filter(
            pk__in=expected_ids,
        ).select_related("warehouse", "product").order_by("product_id", "pk"))
        # Validar TODO antes de la primera reversión. No consultar details:
        # pueden haber cambiado o desaparecido después de la confirmación.
        for original in originals:
            if (original.content_type_id != content_type.pk
                    or original.object_id != document.pk
                    or original.movement_type != MovementType.RETURN_OUT
                    or original.reverses_id is not None):
                raise ValidationError("Movimiento manifestado incompatible con la devolución.")
            if (original.company_id, original.branch_id, original.warehouse_id) != (
                document.company_id, document.branch_id, document.warehouse_id,
            ):
                raise ValidationError("Contexto del movimiento manifestado inconsistente.")
            OperationalContextValidator.validate_inventory(
                document.company, document.branch, original.warehouse, original.product,
            )
            if original.quantity <= 0 or original.reversal_movements.exists():
                raise ValidationError("Salida original inválida o ya revertida.")

        for original in originals:
            StockMovementReversalService.reverse(
                movement=original, reversal_type=MovementType.RETURN_IN, user=user,
            )
        return DocumentService.cancel(document, user=user)
