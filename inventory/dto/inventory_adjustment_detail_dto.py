from dataclasses import dataclass
from decimal import Decimal

@dataclass
class InventoryAdjustmentDetailDTO:
    product_id: int
    quantity: Decimal
