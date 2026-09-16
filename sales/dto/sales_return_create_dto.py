from dataclasses import dataclass
from datetime import date
from typing import Sequence
from .sales_return_detail_dto import SalesReturnDetailDTO

@dataclass(frozen=True)
class SalesReturnCreateDTO:
    sale_id: int
    issue_date: date
    notes: str
    details: Sequence[SalesReturnDetailDTO]
