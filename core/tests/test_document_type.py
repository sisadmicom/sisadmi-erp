from django.db import IntegrityError, transaction
from django.test import TestCase

from core.constants.document_category import DocumentCategory
from core.constants.inventory_behavior import InventoryBehavior
from core.constants.line_behavior import LineBehavior
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
                    line_behavior=LineBehavior.COMMERCIAL,
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


    def test_line_behavior_choices(self):
        self.assertEqual(LineBehavior.choices, [
            ("NONE", "Sin líneas"), ("QUANTITY", "Cantidad"),
            ("VALUED", "Valorada"), ("COMMERCIAL", "Comercial"),
        ])

    def test_canonical_line_behaviors(self):
        for code, behavior in (
            ("SALES_INVOICE", LineBehavior.COMMERCIAL),
            ("PURCHASE_INVOICE", LineBehavior.COMMERCIAL),
            ("INVENTORY_TRANSFER", LineBehavior.QUANTITY),
        ):
            with self.subTest(code=code):
                self.assertEqual(DocumentType.objects.get(code=code).line_behavior, behavior)

    def test_none_is_default_and_valid_without_required_details(self):
        document_type = DocumentType.objects.create(
            code="WITHOUT_LINES", name="Sin líneas", category=DocumentCategory.SALES,
        )
        document_type.refresh_from_db()
        self.assertEqual(document_type.line_behavior, LineBehavior.NONE)
        self.assertFalse(document_type.requires_detail)

    def test_none_cannot_require_details(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentType.objects.create(
                code="INVALID_LINES", name="Inválido", category=DocumentCategory.SALES,
                line_behavior=LineBehavior.NONE, requires_detail=True,
            )

    def test_line_structures_allow_optional_or_required_details(self):
        for behavior in (LineBehavior.QUANTITY, LineBehavior.VALUED, LineBehavior.COMMERCIAL):
            for required in (False, True):
                with self.subTest(behavior=behavior, required=required):
                    document_type = DocumentType.objects.create(
                        code=f"{behavior}_{required}", name="Tipo", category=DocumentCategory.SALES,
                        line_behavior=behavior, requires_detail=required,
                    )
                    document_type.refresh_from_db()
                    self.assertEqual(document_type.line_behavior, behavior)
                    self.assertEqual(document_type.requires_detail, required)

    def test_line_behavior_is_not_nullable(self):
        self.assertFalse(DocumentType._meta.get_field("line_behavior").null)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentType.objects.filter(code="SALES_INVOICE").update(line_behavior=None)
