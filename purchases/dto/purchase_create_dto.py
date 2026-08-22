#purchases/dto/purchase_create_dto.py
from dataclasses import dataclass
from datetime import date
from typing import List

from decimal import Decimal

from purchases.dto.purchase_detail_dto import PurchaseDetailDTO


@dataclass
class PurchaseCreateDTO:

    company_id: int
    branch_id: int
    supplier_id: int

    issue_date: date

    notes: str

    details: List[PurchaseDetailDTO]