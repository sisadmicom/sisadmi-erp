from django.db import IntegrityError, models
from django.db.models.deletion import ProtectedError

from inventory.models import StockMovement
from sales.tests.sale_manifest_test_support import SaleManifestFixture


class SaleMovementModelContractTests(SaleManifestFixture):
    def test_model_contract_and_no_snapshots(self):
        model = self.require_model()
        self.assertEqual(model._meta.get_field("sale").remote_field.model._meta.label, "sales.Sale")
        field = model._meta.get_field("stock_movement")
        self.assertIs(field.remote_field.model, StockMovement)
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        self.assertIs(model._meta.get_field("sale").remote_field.on_delete, models.PROTECT)
        names = {f.name for f in model._meta.get_fields()}
        self.assertNotIn("sale_detail", names)
        for name in ("product", "quantity", "warehouse", "unit_cost", "price", "tax", "status", "lifecycle"):
            self.assertNotIn(name, names)

    def test_required_fields_and_one_to_one(self):
        model = self.require_model()
        self.assertFalse(model._meta.get_field("sale").null)
        self.assertFalse(model._meta.get_field("stock_movement").null)
        self.assertTrue(model._meta.get_field("stock_movement").one_to_one)

    def test_sale_can_have_many_but_movement_cannot_be_reused(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale(lines=[(self.product, 5, 10), (self.product2, 2, 4)]))
        rows = list(model.objects.filter(sale=sale))
        self.assertEqual(len(rows), 2)
        with self.assertRaises(IntegrityError):
            model.objects.create(sale=sale, stock_movement=rows[0].stock_movement)

    def test_protects_sale_and_stock_movement(self):
        model = self.require_model()
        sale = self.confirm(self.make_sale())
        row = model.objects.get(sale=sale)
        with self.assertRaises(ProtectedError):
            sale.delete()
        with self.assertRaises(ProtectedError):
            row.stock_movement.delete()
