from dataclasses import dataclass
from decimal import Decimal


@dataclass
class SaleDetailDTO:

    product_id: int
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal = Decimal("0")