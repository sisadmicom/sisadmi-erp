from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PurchaseReturnDetailDTO:
    purchase_detail_id: int
    quantity: Decimal
