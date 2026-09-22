from decimal import Decimal

from django.db import IntegrityError, models
from django.db.models.fields.related import ForeignKey, OneToOneField
from django.db.models.deletion import ProtectedError

from inventory.models import StockMovement
from purchases.tests.purchase_manifest_test_support import PurchaseManifestFixture


class PurchaseMovementModelContractTests(PurchaseManifestFixture):
    def test_model_exists_with_required_relations(self):
        model = self.model(self)
        if model is None:
            return
        self.assertIsInstance(model._meta.get_field("purchase"), ForeignKey)
        self.assertIsInstance(model._meta.get_field("stock_movement"), OneToOneField)
        self.assertEqual(model._meta.get_field("purchase").remote_field.model._meta.label, "purchases.Purchase")
        self.assertEqual(model._meta.get_field("stock_movement").remote_field.model, StockMovement)
        self.assertEqual(model._meta.get_field("purchase").remote_field.on_delete, models.PROTECT)
        self.assertEqual(model._meta.get_field("stock_movement").remote_field.on_delete, models.PROTECT)

    def test_purchase_movement_has_no_detail_fk_or_snapshots(self):
        model = self.model(self)
        if model is None:
            return
        names = {field.name for field in model._meta.get_fields()}
        self.assertNotIn("purchase_detail", names)
        for name in ("warehouse", "product", "quantity", "unit_cost"):
            self.assertNotIn(name, names)

    def test_one_movement_cannot_be_used_twice_and_purchase_can_have_many(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase([
            (self.product, Decimal("5"), Decimal("10")),
            (self.product_2, Decimal("2"), Decimal("4")),
        ]))
        rows = list(model.objects.filter(purchase=purchase).order_by("pk"))
        self.assertEqual(len(rows), 2)
        with self.assertRaises(IntegrityError):
            model.objects.create(purchase=purchase, stock_movement=rows[0].stock_movement)

    def test_protects_purchase_and_stock_movement(self):
        model = self.model(self)
        if model is None:
            return
        purchase = self.confirm(self.make_purchase())
        movement = self.original_movements(purchase).get()
        manifest = model.objects.get(purchase=purchase, stock_movement=movement)
        with self.assertRaises(ProtectedError):
            purchase.delete()
        with self.assertRaises(ProtectedError):
            movement.delete()
