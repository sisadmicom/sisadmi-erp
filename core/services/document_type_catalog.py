"""Reloadable master data matching the existing core data migrations.

Only missing codes are inserted. Existing definitions, activity and audit data
are never overwritten. Historical migrations remain self-contained.
"""
from django.db import router, transaction

from core.constants.document_type_codes import DocumentTypeCodes as Codes


DOCUMENT_TYPES = (
    (Codes.SALES_INVOICE, "Factura de venta", "SALES", "COMMERCIAL", "OUT", True),
    (Codes.PURCHASE_INVOICE, "Factura de compra", "PURCHASES", "COMMERCIAL", "IN", False),
    (Codes.INVENTORY_TRANSFER, "Transferencia de inventario", "INVENTORY", "QUANTITY", "TRANSFER", False),
    (Codes.INVENTORY_ADJUSTMENT_IN, "Ajuste de inventario de entrada", "INVENTORY", "QUANTITY", "IN", False),
    (Codes.INVENTORY_ADJUSTMENT_OUT, "Ajuste de inventario de salida", "INVENTORY", "QUANTITY", "OUT", False),
    (Codes.SALES_RETURN, "Devolución de venta", "SALES", "COMMERCIAL", "IN", False),
    (Codes.PURCHASE_RETURN, "Devolución de compra", "PURCHASES", "COMMERCIAL", "OUT", False),
)


def ensure_document_types(*, using, apps):
    model = apps.get_model("core", "DocumentType")
    # An older historical schema must keep the semantics of its own migrations.
    if "line_behavior" not in {field.name for field in model._meta.fields}:
        return 0
    if not router.allow_migrate_model(using, model):
        return 0
    created_count = 0
    with transaction.atomic(using=using):
        for code, name, category, lines, inventory, electronic in DOCUMENT_TYPES:
            _, created = model.objects.using(using).get_or_create(
                code=code, defaults={
                    "name": name, "category": category, "line_behavior": lines,
                    "requires_detail": True, "affects_inventory": True,
                    "inventory_behavior": inventory, "can_issue_electronic": electronic,
                    "is_active": True,
                },
            )
            created_count += created
    return created_count


def initialize_document_types(sender, *, using, apps=None, **kwargs):
    if apps is None:
        # flush emits post_migrate without the historical registry supplied
        # by migrate. Its schema is the current installed application schema.
        from django.apps import apps
    ensure_document_types(using=using, apps=apps)
