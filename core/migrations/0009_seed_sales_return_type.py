from django.db import migrations

DATA = dict(code="SALES_RETURN", name="Devolución de venta", category="SALES",
            line_behavior="COMMERCIAL", requires_detail=True, affects_inventory=True,
            inventory_behavior="IN", can_issue_electronic=False, is_active=True)

def seed(apps, schema_editor):
    Model = apps.get_model("core", "DocumentType")
    qs = Model.objects.using(schema_editor.connection.alias)
    obj = qs.filter(code=DATA["code"]).first()
    if obj is None:
        qs.create(**DATA)
    elif any(getattr(obj, k) != v for k, v in DATA.items() if k != "code"):
        raise RuntimeError("DocumentType incompatible: SALES_RETURN")

def unseed(apps, schema_editor):
    Model = apps.get_model("core", "DocumentType")
    Model.objects.using(schema_editor.connection.alias).filter(code=DATA["code"]).delete()

class Migration(migrations.Migration):
    dependencies = [("core", "0008_seed_inventory_adjustment_types")]
    operations = [migrations.RunPython(seed, unseed)]
