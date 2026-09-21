from django.db import models

from core.models import BaseDocumentLine, CommercialAmountsMixin, QuantityLineMixin


class PurchaseReturnDetail(BaseDocumentLine, QuantityLineMixin, CommercialAmountsMixin):
    purchase_return = models.ForeignKey(
        "purchases.PurchaseReturn", on_delete=models.CASCADE, related_name="details",
    )
    purchase_detail = models.ForeignKey(
        "purchases.PurchaseDetail", on_delete=models.PROTECT,
        related_name="purchase_return_details",
    )
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_return", "line"], name="unique_purchase_return_line",
            ),
            models.UniqueConstraint(
                fields=["purchase_return", "purchase_detail"],
                name="unique_purchase_return_purchase_detail",
            ),
        ]
