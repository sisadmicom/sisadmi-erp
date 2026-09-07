import django.db.models.deletion
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError


def require_classified_sequences(apps, schema_editor):
    Sequence = apps.get_model("core", "Sequence")
    alias = schema_editor.connection.alias
    pending = Sequence.objects.using(alias).filter(document_type__isnull=True)
    if pending.exists():
        raise RuntimeError(
            "Existen secuencias históricas pendientes de clasificación "
            "(document_type=NULL). Asigne explícitamente su DocumentType "
            "antes de reintentar la migración. "
            f"Primeros IDs pendientes: {list(pending.order_by('pk').values_list('pk', flat=True)[:20])}."
        )


def require_empty_sequences_for_rollback(apps, schema_editor):
    Sequence = apps.get_model("core", "Sequence")
    alias = schema_editor.connection.alias
    if Sequence.objects.using(alias).exists():
        raise IrreversibleError(
            "No se puede revertir la eliminación de Sequence.code con secuencias "
            "existentes: sus códigos históricos no pueden reconstruirse. "
            "La reversión requiere restaurar una copia de seguridad anterior."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_sequence_document_type"),
    ]

    operations = [
        migrations.RunPython(require_classified_sequences, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="sequence",
            name="document_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sequences",
                to="core.documenttype",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="sequence",
            name="unique_sequence_company_branch_code",
        ),
        migrations.RemoveField(model_name="sequence", name="code"),
        # Runs first on rollback, before any schema change. Codes cannot be
        # reconstructed without inventing replacements, so only an empty table
        # can safely return to the historical schema.
        migrations.RunPython(migrations.RunPython.noop, require_empty_sequences_for_rollback),
    ]
