from django.db import transaction
from core.models import Branch, Company, DocumentType
from catalog.models import Product
from inventory.models import InventoryAdjustment, InventoryAdjustmentDetail, Warehouse
from inventory.validators.inventory_adjustment_validator import InventoryAdjustmentValidator

class InventoryAdjustmentCreator:
    @staticmethod
    @transaction.atomic
    def create(dto, direction):
        company = Company.objects.get(pk=dto.company_id)
        branch = Branch.objects.get(pk=dto.branch_id)
        warehouse = Warehouse.objects.get(pk=dto.warehouse_id)
        products = [Product.objects.get(pk=item.product_id) for item in dto.details]
        document_type = DocumentType.objects.get(code=f"INVENTORY_ADJUSTMENT_{direction}")
        InventoryAdjustmentValidator.validate_create(dto, company, branch, warehouse, products, document_type, direction)
        adjustment = InventoryAdjustment.objects.create(company=company, branch=branch, warehouse=warehouse, document_type=document_type, number="", issue_date=dto.issue_date, notes=dto.notes)
        InventoryAdjustmentDetail.objects.bulk_create([
            InventoryAdjustmentDetail(adjustment=adjustment, line=line, product=product, quantity=item.quantity)
            for line, (item, product) in enumerate(zip(dto.details, products), 1)
        ])
        return adjustment
