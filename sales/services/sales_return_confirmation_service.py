from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError
from core.services.document_service import DocumentService
from inventory.constants.movement_type import MovementType
from inventory.services.stock import IncreaseStock
from sales.models import SalesReturn
from sales.validators.sales_return_validator import SalesReturnValidator
from sales.services.sales_return_calculation import q, confirmed_qty
from sales.services.sale_history import validated_sale_movements
class SalesReturnConfirmationService:
    @staticmethod
    @transaction.atomic
    def execute(sales_return_id,user=None):
        ret=SalesReturn.objects.select_for_update().select_related("sale","company","branch","warehouse","document_type").get(pk=sales_return_id)
        DocumentService.ensure_can_confirm(ret)
        sale=ret.sale.__class__.objects.select_for_update().get(pk=ret.sale_id)
        if sale.status != "CONFIRMED": raise ValidationError("La venta debe estar confirmada.")
        validated_sale_movements(sale, lock=True)
        details=list(ret.details.select_for_update().select_related("sale_detail__product"))
        SalesReturnValidator.validate_persisted(ret)
        for d in details:
            available=d.sale_detail.quantity-confirmed_qty(d.sale_detail, ret.pk)
            if d.quantity>available: raise ValidationError("Cantidad no retornable.")
            if d.quantity == available:
                prior = d.sale_detail.sales_return_details.filter(sales_return__status="CONFIRMED").exclude(sales_return_id=ret.pk)
                for field, source in (("subtotal", "subtotal"), ("tax_amount", "tax_amount"), ("total", "total")):
                    used = prior.aggregate(v=Sum(field))["v"] or 0
                    setattr(d, field, q(getattr(d.sale_detail, source) - used))
                d.save(update_fields=["subtotal", "tax_amount", "total", "updated_at"])
                for tax in d.applied_taxes.all():
                    from sales.models import SalesReturnDetailTax
                    used_base = SalesReturnDetailTax.objects.filter(detail__sale_detail=d.sale_detail, detail__sales_return__status="CONFIRMED", tax_code=tax.tax_code).exclude(detail__sales_return_id=ret.pk).aggregate(v=Sum("base"))["v"] or 0
                    used_amount = SalesReturnDetailTax.objects.filter(detail__sale_detail=d.sale_detail, detail__sales_return__status="CONFIRMED", tax_code=tax.tax_code).exclude(detail__sales_return_id=ret.pk).aggregate(v=Sum("amount"))["v"] or 0
                    original = d.sale_detail.applied_taxes.filter(tax_code=tax.tax_code).first()
                    if original:
                        tax.base=q(original.base-used_base); tax.amount=q(original.amount-used_amount); tax.save(update_fields=["base","amount","updated_at"])
        ret.subtotal=q(sum(d.subtotal for d in details)); ret.tax=q(sum(d.tax_amount for d in details)); ret.total=q(sum(d.total for d in details)); ret.save(update_fields=["subtotal","tax","total","updated_at"])
        DocumentService.confirm(ret,user)
        for d in sorted(details,key=lambda x:x.sale_detail_id):
            IncreaseStock().execute(company=ret.company,branch=ret.branch,warehouse=ret.warehouse,
                product=d.product,quantity=d.quantity,movement_type=MovementType.RETURN_IN,
                document=ret,user=user,notes=f"Devolución {ret.number}")
        return ret
