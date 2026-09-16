from django.db import migrations


DOCUMENT_TYPES = (
    {
        "code": "INVENTORY_ADJUSTMENT_IN", "name": "Ajuste de inventario de entrada",
        "category": "INVENTORY", "line_behavior": "QUANTITY", "requires_detail": True,
        "affects_inventory": True, "inventory_behavior": "IN", "can_issue_electronic": False, "is_active": True,
    },
    {
        "code": "INVENTORY_ADJUSTMENT_OUT", "name": "Ajuste de inventario de salida",
        "category": "INVENTORY", "line_behavior": "QUANTITY", "requires_detail": True,
        "affects_inventory": True, "inventory_behavior": "OUT", "can_issue_electronic": False, "is_active": True,
    },
)

def seed(apps, schema_editor):
    DocumentType = apps.get_model("core", "DocumentType")
    manager = DocumentType.objects.using(schema_editor.connection.alias)
    for data in DOCUMENT_TYPES:
        existing = manager.filter(code=data["code"]).first()
        if existing is None:
            manager.create(**data)
        elif any(getattr(existing, key) != value for key, value in data.items() if key != "code"):
            raise RuntimeError(f"DocumentType incompatible: {data['code']}")

def unseed(apps, schema_editor):
    DocumentType = apps.get_model("core", "DocumentType")
    DocumentType.objects.using(schema_editor.connection.alias).filter(code__in=[d["code"] for d in DOCUMENT_TYPES]).delete()

class Migration(migrations.Migration):
    dependencies = [("core", "0007_document_type_line_behavior")]
    operations = [migrations.RunPython(seed, unseed)]
