from django.db import migrations


DOCUMENT_TYPES = (
    {
        "code": "SALES_INVOICE",
        "name": "Factura de venta",
        "category": "SALES",
        "requires_detail": True,
        "affects_inventory": True,
        "inventory_behavior": "OUT",
        "can_issue_electronic": True,
    },
    {
        "code": "PURCHASE_INVOICE",
        "name": "Factura de compra",
        "category": "PURCHASES",
        "requires_detail": True,
        "affects_inventory": True,
        "inventory_behavior": "IN",
        "can_issue_electronic": False,
    },
    {
        "code": "INVENTORY_TRANSFER",
        "name": "Transferencia de inventario",
        "category": "INVENTORY",
        "requires_detail": True,
        "affects_inventory": True,
        "inventory_behavior": "TRANSFER",
        "can_issue_electronic": False,
    },
)


def create_document_types(apps, schema_editor):
    DocumentType = apps.get_model(
        "core",
        "DocumentType",
    )

    for data in DOCUMENT_TYPES:
        DocumentType.objects.update_or_create(
            code=data["code"],
            defaults=data,
        )


def remove_document_types(apps, schema_editor):
    DocumentType = apps.get_model(
        "core",
        "DocumentType",
    )

    DocumentType.objects.filter(
        code__in=[
            item["code"]
            for item in DOCUMENT_TYPES
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_add_document_type"),
    ]

    operations = [
        migrations.RunPython(
            create_document_types,
            remove_document_types,
        ),
    ]