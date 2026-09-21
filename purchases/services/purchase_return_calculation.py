from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import Sum

from core.constants.document_status import DocumentStatus
from purchases.models import PurchaseReturnDetail


MONEY_FIELDS = ("discount", "subtotal", "tax_amount", "total")


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def snapshot_values(source, quantity):
    """Recalcular contra Returns CONFIRMED; el último parcial absorbe el residuo."""
    prior = PurchaseReturnDetail.objects.filter(
        purchase_detail=source, purchase_return__status=DocumentStatus.CONFIRMED,
    ).aggregate(**{field: Sum(field) for field in ("quantity", *MONEY_FIELDS)})
    prior = {field: value or Decimal("0") for field, value in prior.items()}
    remaining = source.quantity - prior["quantity"]
    if quantity > remaining:
        raise ValidationError("La cantidad excede el saldo disponible para devolución.")
    values = {"unit_price": source.unit_price}
    for field in MONEY_FIELDS:
        original = getattr(source, field)
        amount = (original - prior[field] if quantity == remaining
                  else original * quantity / source.quantity)
        values[field] = money(amount)
    return values


def update_totals(document, details):
    document.subtotal = sum((line.subtotal for line in details), Decimal("0"))
    document.tax = sum((line.tax_amount for line in details), Decimal("0"))
    document.total = sum((line.total for line in details), Decimal("0"))
    document.save(update_fields=["subtotal", "tax", "total", "updated_at"])
