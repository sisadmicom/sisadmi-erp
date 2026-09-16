from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class SalesReturnDetailDTO:
    sale_detail_id: int
    quantity: Decimal
