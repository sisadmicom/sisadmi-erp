from decimal import Decimal

from django.db import models

from core.constants.document_type_codes import DocumentTypeCodes
from core.models import BaseDocument


class PurchaseReturn(BaseDocument):
    DOCUMENT_TYPE_CODE = DocumentTypeCodes.PURCHASE_RETURN

    purchase = models.ForeignKey(
        "purchases.Purchase", on_delete=models.PROTECT, related_name="purchase_returns",
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse", on_delete=models.PROTECT, related_name="purchase_returns",
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
