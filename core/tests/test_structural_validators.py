from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from core.exceptions import EmptyDocument, InvalidPrice, InvalidQuantity
from core.validators.document_detail_validator import DocumentDetailValidator
from core.validators.quantity_line_validator import QuantityLineValidator
from core.validators.commercial_line_validator import CommercialLineValidator


class DocumentDetailValidatorTest(SimpleTestCase):
    def test_details_present_is_valid(self):
        DocumentDetailValidator.validate_required(True)

    def test_details_missing_raises_empty_document(self):
        with self.assertRaises(EmptyDocument):
            DocumentDetailValidator.validate_required(False)


class QuantityLineValidatorTest(SimpleTestCase):
    def test_positive_quantity_is_valid(self):
        QuantityLineValidator.validate(SimpleNamespace(quantity=Decimal("0.000001")))

    def test_zero_quantity_is_invalid(self):
        with self.assertRaises(InvalidQuantity):
            QuantityLineValidator.validate(SimpleNamespace(quantity=Decimal("0")))

    def test_negative_quantity_is_invalid(self):
        with self.assertRaises(InvalidQuantity):
            QuantityLineValidator.validate(SimpleNamespace(quantity=Decimal("-1")))


class CommercialLineValidatorTest(SimpleTestCase):
    def test_positive_quantity_and_price_are_valid(self):
        CommercialLineValidator.validate(SimpleNamespace(
            quantity=Decimal("0.000001"), unit_price=Decimal("0.000001"),
        ))

    def test_zero_price_is_valid(self):
        CommercialLineValidator.validate(SimpleNamespace(quantity=Decimal("1"), unit_price=Decimal("0")))

    def test_nonpositive_quantity_propagates_invalid_quantity(self):
        for quantity in (Decimal("0"), Decimal("-1")):
            with self.subTest(quantity=quantity), self.assertRaises(InvalidQuantity):
                CommercialLineValidator.validate(SimpleNamespace(quantity=quantity, unit_price=Decimal("1")))

    def test_negative_price_is_invalid(self):
        with self.assertRaises(InvalidPrice):
            CommercialLineValidator.validate(SimpleNamespace(quantity=Decimal("1"), unit_price=Decimal("-0.000001")))

    def test_quantity_is_validated_before_price(self):
        # No price attribute: invalid quantity must stop validation first.
        with self.assertRaises(InvalidQuantity):
            CommercialLineValidator.validate(SimpleNamespace(quantity=Decimal("0")))

    def test_reuses_quantity_validator(self):
        line = SimpleNamespace(quantity=Decimal("1"), unit_price=Decimal("2"))
        with patch.object(QuantityLineValidator, "validate", wraps=QuantityLineValidator.validate) as validate:
            CommercialLineValidator.validate(line)
        validate.assert_called_once_with(line)

    def test_other_amounts_are_out_of_scope(self):
        CommercialLineValidator.validate(SimpleNamespace(
            quantity=Decimal("1"), unit_price=Decimal("2"),
            discount=Decimal("-1"), subtotal=Decimal("-1"),
            tax_amount=Decimal("-1"), total=Decimal("-1"),
        ))
