from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, tag

from inventory.constants.movement_type import MovementType
from inventory.models import StockMovement
from inventory.services.stock import DecreaseStock
from purchases.models import PurchaseReturnMovement
from purchases.tests.purchase_return_test_support import (
    PurchaseReturnFixture,
    persisted_state,
    return_api,
)


@tag("c09_purchase_return_exact_capture")
class PurchaseReturnExactCaptureTests(PurchaseReturnFixture, TestCase):
    def multiline_return(self):
        _, Line, *_ = return_api()
        purchase = self.two_line_purchase()
        return self.make_return(purchase=purchase, details=[
            Line(detail.pk, Decimal("3"))
            for detail in purchase.details.order_by("line")
        ])

    def test_confirmation_requests_returned_movement(self):
        original = DecreaseStock.execute
        calls = []

        def observe(instance, *args, **kwargs):
            calls.append(kwargs.copy())
            return original(instance, *args, **kwargs)

        document = self.make_return()
        with patch.object(DecreaseStock, "execute", new=observe):
            self.confirm_return(document)

        self.assertTrue(calls)
        self.assertTrue(all(call.get("return_movement") is True for call in calls))

    def test_multiline_manifest_uses_exact_returned_movement_ids(self):
        original = DecreaseStock.execute
        returned = []

        def observe(instance, *args, **kwargs):
            movement = original(instance, *args, **kwargs)
            self.assertTrue(kwargs.get("return_movement") is True)
            self.assertIsInstance(movement, StockMovement)
            returned.append(movement)
            return movement

        document = self.multiline_return()
        with patch.object(DecreaseStock, "execute", new=observe):
            self.confirm_return(document)

        self.assertEqual(
            set(PurchaseReturnMovement.objects.filter(
                purchase_return=document,
            ).values_list("stock_movement_id", flat=True)),
            {movement.pk for movement in returned},
        )

    def test_manifest_exists_before_next_decrease(self):
        original = DecreaseStock.execute
        calls = 0
        document = self.multiline_return()

        def observe(instance, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.assertEqual(
                    PurchaseReturnMovement.objects.filter(
                        purchase_return=document,
                    ).count(),
                    1,
                )
            return original(instance, *args, **kwargs)

        with patch.object(DecreaseStock, "execute", new=observe):
            self.confirm_return(document)

        self.assertEqual(calls, 2)

    def test_second_manifest_failure_rolls_back_everything(self):
        document = self.multiline_return()
        before = persisted_state()
        before_manifest = list(PurchaseReturnMovement.objects.order_by("pk").values())
        original_create = PurchaseReturnMovement.objects.create
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("C-09 manifest persistence failure")
            return original_create(*args, **kwargs)

        with patch.object(PurchaseReturnMovement.objects, "create", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                self.confirm_return(document)

        self.assertEqual(calls, 2)
        self.assertEqual(persisted_state(), before)
        self.assertEqual(
            list(PurchaseReturnMovement.objects.order_by("pk").values()),
            before_manifest,
        )
