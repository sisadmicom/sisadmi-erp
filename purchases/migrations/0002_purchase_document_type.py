from django.db import migrations, models
import django.db.models.deletion


def backfill_document_type(apps, schema_editor):
    DocumentType = apps.get_model("core", "DocumentType")
    Document = apps.get_model("purchases", "Purchase")
    alias = schema_editor.connection.alias
    document_type = DocumentType.objects.using(alias).get(code="PURCHASE_INVOICE")
    Document.objects.using(alias).filter(document_type__isnull=True).update(
        document_type_id=document_type.pk,
    )


def reverse_backfill_document_type(apps, schema_editor):
    DocumentType = apps.get_model("core", "DocumentType")
    Document = apps.get_model("purchases", "Purchase")
    alias = schema_editor.connection.alias
    document_type = DocumentType.objects.using(alias).get(code="PURCHASE_INVOICE")
    Document.objects.using(alias).filter(document_type_id=document_type.pk).update(
        document_type_id=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_seed_document_types"),
        ("purchases", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchase",
            name="document_type",
            field=models.ForeignKey(
                to="core.documenttype",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_documents",
                editable=False,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_document_type, reverse_backfill_document_type),
        migrations.AlterField(
            model_name="purchase",
            name="document_type",
            field=models.ForeignKey(
                to="core.documenttype",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_documents",
                editable=False,
            ),
        ),
    ]
