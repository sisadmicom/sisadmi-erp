from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from core.constants.document_status import DocumentStatus
from core.exceptions import EmptyDocument, InvalidPrice, InvalidQuantity
from sales.services.sale_validator import SaleValidator


class Details(list):
    def exists(self):
        return bool(self)

    def all(self):
        return self


class SaleValidatorTest(SimpleTestCase):
    def line(self, quantity="1", price="2"):
        return SimpleNamespace(quantity=Decimal(quantity), unit_price=Decimal(price))

    def dto(self, details=None):
        return SimpleNamespace(details=[self.line()] if details is None else details)

    def sale(self, details=None, status=DocumentStatus.DRAFT):
        return SimpleNamespace(status=status, details=Details([self.line()] if details is None else details))

    def test_validate_valid_sale(self):
        SaleValidator.validate(self.dto())

    def test_validate_without_details(self):
        with self.assertRaises(EmptyDocument):
            SaleValidator.validate(self.dto(details=[]))

    def test_validate_zero_quantity(self):
        with self.assertRaises(InvalidQuantity):
            SaleValidator.validate(self.dto(details=[self.line(quantity="0")]))

    def test_validate_negative_quantity(self):
        with self.assertRaises(InvalidQuantity):
            SaleValidator.validate(self.dto(details=[self.line(quantity="-1")]))

    def test_validate_zero_price_is_valid(self):
        SaleValidator.validate(self.dto(details=[self.line(price="0")]))

    def test_validate_negative_price(self):
        with self.assertRaises(InvalidPrice):
            SaleValidator.validate(self.dto(details=[self.line(price="-0.01")]))

    def test_confirmation_valid_draft(self):
        SaleValidator.validate_confirmation(self.sale())

    def test_confirmation_without_details(self):
        with self.assertRaises(EmptyDocument):
            SaleValidator.validate_confirmation(self.sale(details=[]))

    def test_confirmation_zero_quantity(self):
        with self.assertRaises(InvalidQuantity):
            SaleValidator.validate_confirmation(self.sale(details=[self.line(quantity="0")]))

    def test_confirmation_negative_quantity(self):
        with self.assertRaises(InvalidQuantity):
            SaleValidator.validate_confirmation(self.sale(details=[self.line(quantity="-1")]))

    def test_confirmation_zero_price_is_valid(self):
        SaleValidator.validate_confirmation(self.sale(details=[self.line(price="0")]))

    def test_confirmation_negative_price(self):
        with self.assertRaises(InvalidPrice):
            SaleValidator.validate_confirmation(self.sale(details=[self.line(price="-0.01")]))

    def test_confirmation_validator_does_not_own_lifecycle(self):
        for status in (DocumentStatus.CONFIRMED, DocumentStatus.CANCELLED):
            with self.subTest(status=status):
                SaleValidator.validate_confirmation(self.sale(status=status))

    def test_cancellation_confirmed_is_valid(self):
        SaleValidator.validate_cancellation(self.sale(status=DocumentStatus.CONFIRMED))

    def test_cancellation_cancelled_keeps_lifecycle_error(self):
        with self.assertRaisesMessage(ValueError, "La venta ya fue anulada."):
            SaleValidator.validate_cancellation(self.sale(status=DocumentStatus.CANCELLED))

    def test_cancellation_draft_keeps_lifecycle_error(self):
        with self.assertRaisesMessage(ValueError, "Solo se pueden cancelar ventas confirmadas."):
            SaleValidator.validate_cancellation(self.sale())

    def test_cancellation_without_details_keeps_value_error(self):
        with self.assertRaisesMessage(ValueError, "La venta no tiene detalles."):
            SaleValidator.validate_cancellation(self.sale(details=[], status=DocumentStatus.CONFIRMED))

    def test_cancellation_nonpositive_quantity_keeps_value_error(self):
        for quantity in ("0", "-1"):
            with self.subTest(quantity=quantity), self.assertRaisesMessage(ValueError, "Cantidad inválida."):
                SaleValidator.validate_cancellation(self.sale(
                    details=[self.line(quantity=quantity)], status=DocumentStatus.CONFIRMED,
                ))

    def test_cancellation_negative_price_keeps_value_error(self):
        with self.assertRaisesMessage(ValueError, "Precio inválido."):
            SaleValidator.validate_cancellation(self.sale(
                details=[self.line(price="-0.01")], status=DocumentStatus.CONFIRMED,
            ))
