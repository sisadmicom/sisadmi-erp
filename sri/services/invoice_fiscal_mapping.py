"""SRI serialization codes, separate from internal catalog identifiers.

Source: SRI technical sheet 2.34, tables 17 and 24 (see schemas/provenance).
This translates an already resolved snapshot; it never selects a tax/rate.
"""
from decimal import Decimal

from catalog.constants.tax_category import TaxCategory
from sales.constants.payment_method import PaymentMethod


PAYMENT_CODES = {
    PaymentMethod.NON_FINANCIAL: "01", PaymentMethod.DEBT_OFFSET: "15",
    PaymentMethod.DEBIT_CARD: "16", PaymentMethod.ELECTRONIC_MONEY: "17",
    PaymentMethod.PREPAID_CARD: "18", PaymentMethod.CREDIT_CARD: "19",
    PaymentMethod.FINANCIAL_OTHER: "20", PaymentMethod.TITLE_ENDORSEMENT: "21",
}
IDENTIFICATION_CODES = {"RUC": "04", "CEDULA": "05", "PASSPORT": "06", "FOREIGN_ID": "08"}
VAT_RATE_CODES = {Decimal(rate): code for rate, code in (
    ("12", "2"), ("14", "3"), ("15", "4"), ("5", "5"), ("13", "10"),
)}


def vat_codes(snapshot):
    if snapshot.tax_type != "IVA":
        raise ValueError("La factura simple requiere un mapeo fiscal explícito para impuestos distintos de IVA.")
    category, rate = snapshot.tax_category, snapshot.rate
    special = {
        TaxCategory.VAT_ZERO_RATED: "0", TaxCategory.VAT_NOT_SUBJECT: "6",
        TaxCategory.VAT_EXEMPT: "7",
    }
    if category in special and rate in (None, Decimal("0")):
        return "2", special[category]
    # Positive legacy snapshots remain unambiguous: the persisted IVA rate
    # determines its percentage code, never the internal Tax.code/name.
    if category in (None, "", TaxCategory.VAT_STANDARD) and rate in VAT_RATE_CODES:
        return "2", VAT_RATE_CODES[rate]
    raise ValueError("El snapshot de IVA no tiene una clasificación y tarifa fiscal compatibles.")
