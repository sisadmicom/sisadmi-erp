from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction

from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.stock import DecreaseStock
from purchases.models import Purchase, PurchaseReturn, PurchaseReturnMovement
from purchases.services.purchase_return_calculation import MONEY_FIELDS, snapshot_values, update_totals
from purchases.services.purchase_return_history import purchase_history
from purchases.validators.purchase_return_validator import PurchaseReturnValidator


class PurchaseReturnConfirmationService:
    @staticmethod
    @transaction.atomic
    def execute(purchase_return_id, user=None):
        # Siempre Purchase -> Return, también en cancelación. La lectura inicial
        # solo descubre la FK; toda decisión usa instancias frescas bajo lock.
        purchase_id = PurchaseReturn.objects.values_list("purchase_id", flat=True).get(pk=purchase_return_id)
        purchase = Purchase.objects.select_for_update().get(pk=purchase_id)
        document = PurchaseReturn.objects.select_for_update().get(pk=purchase_return_id)
        DocumentService.ensure_can_confirm(document)
        PurchaseReturnValidator.validate_context(document, purchase)
        details = list(document.details.select_for_update(of=("self",)).select_related(
            "purchase_detail__product", "product",
        ))
        PurchaseReturnValidator.validate_lines(
            purchase, [(line.purchase_detail, line.quantity) for line in details],
        )
        warehouse, costs = purchase_history(purchase)
        if document.warehouse_id != warehouse.pk:
            raise ValidationError("La bodega de devolución no coincide con la historia PURCHASE.")
        for line in details:
            if line.product_id != line.purchase_detail.product_id:
                raise ValidationError("Snapshot de producto inconsistente.")
            for field, value in snapshot_values(line.purchase_detail, line.quantity).items():
                setattr(line, field, value)
            line.save(update_fields=["unit_price", *MONEY_FIELDS, "updated_at"])
        update_totals(document, details)

        movements = StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(document), object_id=document.pk,
        )
        if movements.exists() or document.movement_manifest.exists():
            raise ValidationError("Un borrador no puede tener historia operacional previa.")
        DocumentService.confirm(document, user=user)
        for line in sorted(details, key=lambda item: (item.product_id, item.purchase_detail_id)):
            movement = DecreaseStock().execute(
                company=document.company, branch=document.branch, warehouse=warehouse,
                product=line.product, quantity=line.quantity, movement_type=MovementType.RETURN_OUT,
                unit_cost=costs[line.product_id], document=document, user=user,
                notes=f"Devolución {document.number}",
                return_movement=True,
            )
            PurchaseReturnMovement.objects.create(purchase_return=document, stock_movement=movement)

        actual_ids = set(movements.filter(
            movement_type=MovementType.RETURN_OUT, reverses__isnull=True,
        ).values_list("pk", flat=True))
        expected_ids = set(document.movement_manifest.values_list("stock_movement_id", flat=True))
        if expected_ids != actual_ids:
            raise ValidationError("El manifiesto no coincide con las salidas originales.")
        return document
