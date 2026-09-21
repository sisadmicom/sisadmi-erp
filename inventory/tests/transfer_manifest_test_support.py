from decimal import Decimal

from django.apps import apps
from django.contrib.contenttypes.models import ContentType

from catalog.models import Product
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Transfer
from inventory.tests.test_confirm_transfer import TransferFixture
from inventory.use_cases.cancel_transfer import CancelTransfer
from inventory.use_cases.confirm_transfer import ConfirmTransfer


class TransferManifestFixture(TransferFixture):
    """Fixtures for the C-04 contract; no production fallback is allowed."""

    def pair_model(self):
        try:
            return apps.get_model("inventory", "TransferMovementPair")
        except LookupError:
            self.assertIsNotNone(None, "TransferMovementPair is required by the C-04 contract.")

    def document_movements(self, transfer):
        return StockMovement.objects.filter(
            content_type=ContentType.objects.get_for_model(Transfer),
            object_id=transfer.pk,
        ).order_by("pk")

    def original_movements(self, transfer):
        return self.document_movements(transfer).filter(reverses__isnull=True)

    def confirmed_transfer(self, quantity="5"):
        transfer = self.create_transfer(quantity)
        ConfirmTransfer.execute(transfer_id=transfer.pk, user=None)
        transfer.refresh_from_db()
        return transfer

    def confirmed_pair(self, quantity="5"):
        transfer = self.confirmed_transfer(quantity)
        return transfer, self.pair_model().objects.get(transfer=transfer)

    def add_second_product(self):
        product = Product.objects.create(company=self.company, code="P002", name="Segundo producto")
        for warehouse, quantity in ((self.source_warehouse, "20"), (self.destination_warehouse, "5")):
            Stock.objects.create(
                company=self.company, branch=self.branch, warehouse=warehouse,
                product=product, quantity=Decimal(quantity), reserved_quantity=Decimal("0"),
            )
        return product

    def create_two_line_transfer(self):
        from inventory.dto.transfer_create_dto import TransferCreateDTO
        from inventory.dto.transfer_detail_dto import TransferDetailDTO
        other = self.add_second_product()
        transfer = self.create_transfer("5")
        transfer.details.create(product=other, line=2, quantity=Decimal("7"))
        return transfer

    def confirmed_two_line_transfer(self):
        transfer = self.create_two_line_transfer()
        ConfirmTransfer.execute(transfer_id=transfer.pk, user=None)
        transfer.refresh_from_db()
        return transfer

    def cancel_and_expect_rejection(self, transfer):
        before = list(self.document_movements(transfer).values_list("pk", "movement_type", "reverses_id"))
        with self.assertRaises(Exception):
            CancelTransfer.execute(transfer_id=transfer.pk, user=None)
        self.assertFalse(self.document_movements(transfer).filter(reverses__isnull=False).exists())
        self.assertEqual(
            list(self.document_movements(transfer).values_list("pk", "movement_type", "reverses_id")),
            before,
        )
