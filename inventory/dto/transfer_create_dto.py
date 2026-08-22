from dataclasses import dataclass
from datetime import date
from typing import List

from inventory.dto.transfer_detail_dto import (
    TransferDetailDTO,
)


@dataclass
class TransferCreateDTO:

    company_id: int
    branch_id: int

    source_warehouse_id: int
    destination_warehouse_id: int

    issue_date: date

    notes: str

    details: List[TransferDetailDTO]
