from django.db import transaction
from django.core.exceptions import ValidationError
from core.constants.document_type_codes import DocumentTypeCodes
from core.models import DocumentType
from sales.models import SalesReturn, SalesReturnDetail, SalesReturnDetailTax
from sales.validators.sales_return_validator import SalesReturnValidator
from sales.services.sales_return_calculation import q, confirmed_qty
class SalesReturnCreator:
    @staticmethod
    @transaction.atomic
    def execute(dto):
        from sales.models import Sale, SaleDetail
        try: sale=Sale.objects.select_related("company","branch","warehouse").get(pk=dto.sale_id)
        except Sale.DoesNotExist: raise ValidationError("Venta inexistente.")
        dtype=DocumentType.objects.get(code=DocumentTypeCodes.SALES_RETURN)
        pairs=[]; seen=set()
        for item in dto.details:
            if item.sale_detail_id in seen: raise ValidationError("Línea repetida.")
            seen.add(item.sale_detail_id)
            try: sd=SaleDetail.objects.select_related("product").get(pk=item.sale_detail_id)
            except SaleDetail.DoesNotExist: raise ValidationError("Línea inexistente.")
            pairs.append((sd,item.quantity))
        SalesReturnValidator.validate_type(dtype)
        SalesReturnValidator.validate_creation(sale,pairs)
        ret=SalesReturn.objects.create(company=sale.company,branch=sale.branch,document_type=dtype,
             sale=sale,warehouse=sale.warehouse,issue_date=dto.issue_date,notes=dto.notes or "",
             number="",subtotal=0,tax=0,total=0)
        total_sub=total_tax=total=0
        for i,(sd,qty) in enumerate(pairs,1):
            vals={"unit_price":sd.unit_price,"discount":q(sd.discount*qty/sd.quantity),
                  "subtotal":q(sd.subtotal*qty/sd.quantity),"tax_amount":q(sd.tax_amount*qty/sd.quantity),
                  "total":q(sd.total*qty/sd.quantity)}
            d=SalesReturnDetail.objects.create(sales_return=ret,sale_detail=sd,product=sd.product,line=i,quantity=qty,**vals)
            for tax in sd.applied_taxes.all():
                SalesReturnDetailTax.objects.create(detail=d,tax=tax.tax,tax_code=tax.tax_code,tax_name=tax.tax_name,
                    tax_type=tax.tax_type,rate=tax.rate,base=q(tax.base*qty/sd.quantity),amount=q(tax.amount*qty/sd.quantity))
            total_sub+=vals["subtotal"]; total_tax+=vals["tax_amount"]; total+=vals["total"]
        ret.subtotal=q(total_sub); ret.tax=q(total_tax); ret.total=q(total); ret.save(update_fields=["subtotal","tax","total","updated_at"])
        return ret
