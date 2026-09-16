from django.db import models
from core.models import BaseDocumentLine, QuantityLineMixin, CommercialAmountsMixin
from catalog.models import Product
from .sales_return import SalesReturn
from .sale_detail import SaleDetail

class SalesReturnDetail(BaseDocumentLine, QuantityLineMixin, CommercialAmountsMixin):
    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name="details")
    sale_detail = models.ForeignKey(SaleDetail, on_delete=models.PROTECT, related_name="sales_return_details")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["sales_return", "line"], name="unique_sales_return_line"),
            models.UniqueConstraint(fields=["sales_return", "sale_detail"], name="unique_sales_return_sale_detail"),
        ]
