from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from core.constants.document_status import DocumentStatus
Q=Decimal("0.01")
def q(v): return Decimal(v).quantize(Q, rounding=ROUND_HALF_UP)
def confirmed_qty(sale_detail, exclude_id=None):
    from sales.models import SalesReturnDetail
    qs=SalesReturnDetail.objects.filter(sale_detail=sale_detail, sales_return__status=DocumentStatus.CONFIRMED)
    if exclude_id: qs=qs.exclude(sales_return_id=exclude_id)
    return qs.aggregate(v=Sum("quantity"))["v"] or Decimal("0")
def snapshot_values(sd, qty, previous=None):
    sold=sd.quantity
    ratio=qty/sold
    prev=previous or {}
    vals={}
    for name in ("subtotal","tax_amount","total"):
        original=getattr(sd,name)
        vals[name]=q(original-prev.get(name,Decimal("0"))) if qty == sold-(prev.get("quantity",Decimal("0"))) else q(original*ratio)
    vals["unit_price"]=sd.unit_price
    vals["discount"]=q(sd.discount*ratio)
    return vals
