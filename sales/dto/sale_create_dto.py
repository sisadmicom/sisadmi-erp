from dataclasses import dataclass
from datetime import date
from typing import List

from sales.dto.sale_detail_dto import SaleDetailDTO


@dataclass
class SaleCreateDTO:

    company_id: int
    branch_id: int
    customer_id: int
    warehouse_id: int

    issue_date: date

    notes: str

    details: List[SaleDetailDTO]