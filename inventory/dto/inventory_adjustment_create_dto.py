from dataclasses import dataclass
from datetime import date
from typing import List
from .inventory_adjustment_detail_dto import InventoryAdjustmentDetailDTO

@dataclass
class InventoryAdjustmentCreateDTO:
    company_id: int
    branch_id: int
    warehouse_id: int
    issue_date: date
    notes: str
    details: List[InventoryAdjustmentDetailDTO]
