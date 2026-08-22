from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class KardexRow:
    """
    Representa una línea del Kardex.

    Es un DTO, no un modelo de Django.
    """

    movement_date: datetime

    movement_type: str

    document: str | None

    document_number: str | None

    document_type: str | None

    warehouse_name: str

    quantity_in: Decimal

    quantity_out: Decimal

    balance: Decimal

    notes: str