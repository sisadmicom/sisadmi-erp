from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.test import SimpleTestCase

from core.models import BaseDocumentLine, QuantityLineMixin, CommercialAmountsMixin
from core.models.base import BaseModel
from inventory.models import TransferDetail
from purchases.models import PurchaseDetail
from sales.models import SaleDetail


class DocumentLineArchitectureTest(SimpleTestCase):
    commercial_fields = {"unit_price", "discount", "subtotal", "tax_amount", "total"}

    def test_line_abstractions_are_abstract(self):
        for model in (BaseDocumentLine, QuantityLineMixin, CommercialAmountsMixin):
            with self.subTest(model=model.__name__):
                self.assertTrue(model._meta.abstract)

    def test_base_document_line_only_adds_line_to_base_model(self):
        inherited_fields = {field.name for field in BaseModel._meta.fields}
        self.assertTrue(issubclass(BaseDocumentLine, BaseModel))
        self.assertEqual(
            {field.name for field in BaseDocumentLine._meta.fields},
            inherited_fields | {"line"},
        )
        self.assertIsInstance(BaseDocumentLine._meta.get_field("line"), models.PositiveIntegerField)

    def test_quantity_mixin_only_defines_quantity(self):
        self.assertEqual({field.name for field in QuantityLineMixin._meta.fields}, {"quantity"})
        field = QuantityLineMixin._meta.get_field("quantity")
        self.assertIsInstance(field, models.DecimalField)
        self.assertEqual((field.max_digits, field.decimal_places), (18, 6))
        self.assertFalse(field.has_default())

    def test_commercial_mixin_only_defines_amounts(self):
        self.assertEqual(
            {field.name for field in CommercialAmountsMixin._meta.fields}, self.commercial_fields,
        )
        for name in self.commercial_fields:
            with self.subTest(field=name):
                field = CommercialAmountsMixin._meta.get_field(name)
                self.assertIsInstance(field, models.DecimalField)
                self.assertEqual((field.max_digits, field.decimal_places), (18, 6 if name == "unit_price" else 2))
                self.assertEqual(field.default, 0)

    def test_commercial_details_keep_quantity_and_amounts(self):
        for model in (SaleDetail, PurchaseDetail):
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, BaseDocumentLine))
                self.assertTrue(issubclass(model, QuantityLineMixin))
                self.assertTrue(issubclass(model, CommercialAmountsMixin))
                self.assertEqual(
                    (model._meta.get_field("quantity").max_digits, model._meta.get_field("quantity").decimal_places),
                    (18, 6),
                )
                for name in self.commercial_fields:
                    field = model._meta.get_field(name)
                    self.assertEqual((field.max_digits, field.decimal_places), (18, 6 if name == "unit_price" else 2))
                    self.assertEqual(field.default, 0)

    def test_transfer_detail_has_no_commercial_structure(self):
        self.assertTrue(issubclass(TransferDetail, BaseDocumentLine))
        self.assertTrue(issubclass(TransferDetail, QuantityLineMixin))
        self.assertFalse(issubclass(TransferDetail, CommercialAmountsMixin))
        self.assertIsInstance(TransferDetail._meta.get_field("line"), models.PositiveIntegerField)
        quantity = TransferDetail._meta.get_field("quantity")
        self.assertEqual((quantity.max_digits, quantity.decimal_places), (18, 6))
        for name in self.commercial_fields:
            with self.subTest(field=name):
                with self.assertRaises(FieldDoesNotExist):
                    TransferDetail._meta.get_field(name)
                self.assertFalse(hasattr(TransferDetail, name))
                self.assertFalse(hasattr(TransferDetail(), name))

    def test_concrete_lines_keep_base_model_infrastructure(self):
        for model in (SaleDetail, PurchaseDetail, TransferDetail):
            with self.subTest(model=model.__name__):
                self.assertFalse(model._meta.abstract)
                self.assertTrue(issubclass(model, BaseModel))
                for field in BaseModel._meta.fields:
                    inherited = model._meta.get_field(field.name)
                    self.assertIsInstance(inherited, type(field))
