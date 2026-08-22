from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PurchaseDetailDTO:
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal = Decimal("0")