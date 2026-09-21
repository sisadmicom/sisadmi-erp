from dataclasses import dataclass
from datetime import date
from typing import Sequence

from .purchase_return_detail_dto import PurchaseReturnDetailDTO


@dataclass
class PurchaseReturnCreateDTO:
    purchase_id: int
    issue_date: date
    notes: str
    details: Sequence[PurchaseReturnDetailDTO]
