from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from core.exceptions import EmptyDocument, InvalidPrice, InvalidQuantity, ValidationException
from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.validators.purchase_validator import PurchaseValidator


class Details(list):
    def all(self):
        return self

    def exists(self):
        return bool(self)


class PurchaseValidatorTest(SimpleTestCase):
    def detail(self, quantity="1", price="2", discount="0", product_id=1):
        return PurchaseDetailDTO(
            product_id=product_id, quantity=Decimal(quantity),
            unit_price=Decimal(price), discount=Decimal(discount),
        )

    def dto(self, details=None, **overrides):
        data = dict(
            company_id=1, branch_id=1, supplier_id=1, issue_date=date(2026, 1, 1),
            notes="", details=[self.detail()] if details is None else details,
        )
        data.update(overrides)
        return PurchaseCreateDTO(**data)

    def purchase(self, details=None, status="DRAFT", supplier=True):
        return SimpleNamespace(
            supplier=object() if supplier else None,
            details=Details([self.detail()] if details is None else details),
            is_confirmed=lambda: status == "CONFIRMED",
            is_cancelled=lambda: status == "CANCELLED",
        )

    def test_create_valid_purchase(self):
        PurchaseValidator.validate_create(self.dto())

    def test_create_without_details(self):
        with self.assertRaises(EmptyDocument):
            PurchaseValidator.validate_create(self.dto(details=[]))

    def test_create_zero_quantity(self):
        with self.assertRaises(InvalidQuantity):
            PurchaseValidator.validate_create(self.dto(details=[self.detail(quantity="0")]))

    def test_create_negative_quantity(self):
        with self.assertRaises(InvalidQuantity):
            PurchaseValidator.validate_create(self.dto(details=[self.detail(quantity="-1")]))

    def test_create_zero_price_is_valid(self):
        PurchaseValidator.validate_create(self.dto(details=[self.detail(price="0")]))

    def test_create_negative_price(self):
        with self.assertRaises(InvalidPrice):
            PurchaseValidator.validate_create(self.dto(details=[self.detail(price="-0.01")]))

    def test_create_invalid_product_keeps_validation_exception(self):
        for product_id in (0, -1):
            with self.subTest(product_id=product_id), self.assertRaisesMessage(ValidationException, "Producto inválido."):
                PurchaseValidator.validate_create(self.dto(details=[self.detail(product_id=product_id)]))

    def test_create_negative_discount_keeps_validation_exception(self):
        with self.assertRaisesMessage(ValidationException, "El descuento no puede ser negativo."):
            PurchaseValidator.validate_create(self.dto(details=[self.detail(discount="-1")]))

    def test_create_invalid_context_keeps_validation_exception(self):
        for field, message in (
            ("company_id", "Empresa inválida."),
            ("branch_id", "Sucursal inválida."),
            ("supplier_id", "Proveedor inválido."),
        ):
            for value in (0, -1):
                with self.subTest(field=field, value=value), self.assertRaisesMessage(ValidationException, message):
                    PurchaseValidator.validate_create(self.dto(**{field: value}))

    def test_confirmation_valid_purchase(self):
        PurchaseValidator.validate_confirmation(self.purchase())

    def test_confirmation_without_details(self):
        with self.assertRaises(EmptyDocument):
            PurchaseValidator.validate_confirmation(self.purchase(details=[]))

    def test_confirmation_zero_quantity(self):
        with self.assertRaises(InvalidQuantity):
            PurchaseValidator.validate_confirmation(self.purchase(details=[self.detail(quantity="0")]))

    def test_confirmation_negative_quantity(self):
        with self.assertRaises(InvalidQuantity):
            PurchaseValidator.validate_confirmation(self.purchase(details=[self.detail(quantity="-1")]))

    def test_confirmation_zero_price_is_valid(self):
        PurchaseValidator.validate_confirmation(self.purchase(details=[self.detail(price="0")]))

    def test_confirmation_negative_price(self):
        with self.assertRaises(InvalidPrice):
            PurchaseValidator.validate_confirmation(self.purchase(details=[self.detail(price="-0.01")]))

    def test_confirmation_validator_does_not_own_lifecycle(self):
        for status in ("CONFIRMED", "CANCELLED"):
            with self.subTest(status=status):
                PurchaseValidator.validate_confirmation(self.purchase(status=status))

    def test_confirmation_requires_supplier(self):
        with self.assertRaisesMessage(ValueError, "Debe seleccionar un proveedor."):
            PurchaseValidator.validate_confirmation(self.purchase(supplier=False))

    def test_cancellation_valid_purchase(self):
        PurchaseValidator.validate_cancellation(self.purchase(status="CONFIRMED"))

    def test_cancellation_validator_does_not_own_lifecycle(self):
        for status in ("DRAFT", "CANCELLED"):
            with self.subTest(status=status):
                PurchaseValidator.validate_cancellation(self.purchase(status=status))

    def test_cancellation_without_details_keeps_value_error(self):
        with self.assertRaisesMessage(ValueError, "La compra no tiene productos."):
            PurchaseValidator.validate_cancellation(self.purchase(details=[], status="CONFIRMED"))

    def test_cancellation_nonpositive_quantity_keeps_product_message(self):
        for quantity in ("0", "-1"):
            line = self.detail(quantity=quantity)
            line.product = SimpleNamespace(name="Producto de prueba")
            with self.subTest(quantity=quantity), self.assertRaisesMessage(ValueError, "Producto de prueba: cantidad inválida."):
                PurchaseValidator.validate_cancellation(self.purchase(details=[line], status="CONFIRMED"))

    def test_cancellation_does_not_add_price_or_discount_validation(self):
        PurchaseValidator.validate_cancellation(self.purchase(
            details=[self.detail(price="-1", discount="-1")], status="CONFIRMED",
        ))
