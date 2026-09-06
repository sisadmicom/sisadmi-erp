from django.db import IntegrityError, transaction
from django.test import TestCase

from core.constants.document_category import DocumentCategory
from core.constants.inventory_behavior import InventoryBehavior
from core.models import DocumentType


class DocumentTypeTest(TestCase):

    def test_sales_invoice_catalog_definition(self):
        document_type = DocumentType.objects.get(
            code="SALES_INVOICE"
        )

        self.assertEqual(
            document_type.name,
            "Factura de venta",
        )

        self.assertEqual(
            document_type.category,
            DocumentCategory.SALES,
        )

        self.assertTrue(
            document_type.requires_detail
        )

        self.assertTrue(
            document_type.affects_inventory
        )

        self.assertEqual(
            document_type.inventory_behavior,
            InventoryBehavior.OUT,
        )

        self.assertTrue(
            document_type.can_issue_electronic
        )

        self.assertTrue(
            document_type.is_active
        )

    def test_purchase_invoice_catalog_definition(self):
        document_type = DocumentType.objects.get(
            code="PURCHASE_INVOICE"
        )

        self.assertEqual(
            document_type.name,
            "Factura de compra",
        )

        self.assertEqual(
            document_type.category,
            DocumentCategory.PURCHASES,
        )

        self.assertTrue(
            document_type.requires_detail
        )

        self.assertTrue(
            document_type.affects_inventory
        )

        self.assertEqual(
            document_type.inventory_behavior,
            InventoryBehavior.IN,
        )

        self.assertFalse(
            document_type.can_issue_electronic
        )

    def test_inventory_transfer_catalog_definition(self):
        document_type = DocumentType.objects.get(
            code="INVENTORY_TRANSFER"
        )

        self.assertEqual(
            document_type.name,
            "Transferencia de inventario",
        )

        self.assertEqual(
            document_type.category,
            DocumentCategory.INVENTORY,
        )

        self.assertTrue(
            document_type.requires_detail
        )

        self.assertTrue(
            document_type.affects_inventory
        )

        self.assertEqual(
            document_type.inventory_behavior,
            InventoryBehavior.TRANSFER,
        )

        self.assertFalse(
            document_type.can_issue_electronic
        )

    def test_document_type_code_must_be_unique(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DocumentType.objects.create(
                    code="SALES_INVOICE",
                    name="Duplicado",
                    category=DocumentCategory.SALES,
                    requires_detail=True,
                    affects_inventory=True,
                    inventory_behavior=InventoryBehavior.OUT,
                    can_issue_electronic=True,
                )

    def test_non_inventory_document_must_use_none_behavior(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DocumentType.objects.create(
                    code="INVALID_INVENTORY_TYPE",
                    name="Tipo inválido",
                    category=DocumentCategory.SALES,
                    requires_detail=False,
                    affects_inventory=False,
                    inventory_behavior=InventoryBehavior.OUT,
                    can_issue_electronic=False,
                )
