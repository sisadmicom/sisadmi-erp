from django.db import migrations


DATA = dict(
    code="PURCHASE_RETURN", name="Devolución de compra", category="PURCHASES",
    line_behavior="COMMERCIAL", requires_detail=True, affects_inventory=True,
    inventory_behavior="OUT", can_issue_electronic=False, is_active=True,
)


def seed(apps, schema_editor):
    model = apps.get_model("core", "DocumentType")
    rows = model.objects.using(schema_editor.connection.alias)
    existing = rows.filter(code=DATA["code"]).first()
    if existing is None:
        rows.create(**DATA)
    elif any(getattr(existing, key) != value for key, value in DATA.items()):
        raise RuntimeError("DocumentType incompatible: PURCHASE_RETURN")


def unseed(apps, schema_editor):
    model = apps.get_model("core", "DocumentType")
    model.objects.using(schema_editor.connection.alias).filter(code=DATA["code"]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0009_seed_sales_return_type")]
    operations = [migrations.RunPython(seed, unseed)]
