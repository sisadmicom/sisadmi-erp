from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TransferDetailDTO:

    product_id: int

    quantity: Decimal
