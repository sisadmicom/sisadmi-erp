from django.db import models
from core.models import BaseModel
from catalog.models import Tax
from .sales_return_detail import SalesReturnDetail

class SalesReturnDetailTax(BaseModel):
    detail = models.ForeignKey(SalesReturnDetail, on_delete=models.CASCADE, related_name="applied_taxes")
    tax = models.ForeignKey(Tax, on_delete=models.PROTECT, null=True, blank=True)
    tax_code = models.CharField(max_length=30)
    tax_name = models.CharField(max_length=100)
    tax_type = models.CharField(max_length=20)
    rate = models.DecimalField(max_digits=8, decimal_places=4)
    base = models.DecimalField(max_digits=18, decimal_places=2)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
