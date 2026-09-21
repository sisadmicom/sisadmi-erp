from django.core.exceptions import ValidationError
from django.db import transaction

from core.constants.document_type_codes import DocumentTypeCodes
from core.models import DocumentType
from purchases.models import Purchase, PurchaseDetail, PurchaseReturn, PurchaseReturnDetail
from purchases.services.purchase_return_calculation import snapshot_values, update_totals
from purchases.services.purchase_return_history import purchase_history
from purchases.validators.purchase_return_validator import PurchaseReturnValidator


class PurchaseReturnCreator:
    @staticmethod
    @transaction.atomic
    def execute(dto):
        try:
            purchase = Purchase.objects.select_for_update().get(pk=dto.purchase_id)
        except Purchase.DoesNotExist:
            raise ValidationError("Compra inexistente.") from None
        pairs = []
        for item in dto.details:
            try:
                source = PurchaseDetail.objects.select_related("product").get(pk=item.purchase_detail_id)
            except PurchaseDetail.DoesNotExist:
                raise ValidationError("Línea de compra inexistente.") from None
            pairs.append((source, item.quantity))
        PurchaseReturnValidator.validate_lines(purchase, pairs)
        warehouse, _ = purchase_history(purchase)
        document_type = DocumentType.objects.get(code=DocumentTypeCodes.PURCHASE_RETURN)
        PurchaseReturnValidator.validate_type(document_type)
        document = PurchaseReturn.objects.create(
            company=purchase.company, branch=purchase.branch, purchase=purchase,
            warehouse=warehouse, document_type=document_type, number="",
            issue_date=dto.issue_date, notes=dto.notes or "",
        )
        details = []
        for line, (source, quantity) in enumerate(pairs, 1):
            details.append(PurchaseReturnDetail.objects.create(
                purchase_return=document, purchase_detail=source, product=source.product,
                line=line, quantity=quantity, **snapshot_values(source, quantity),
            ))
        update_totals(document, details)
        return document
