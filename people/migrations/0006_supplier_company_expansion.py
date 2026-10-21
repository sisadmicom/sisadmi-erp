"""Expansión de esquema sin backfill ni clasificación de Supplier.

Aplicar/revertir en una ventana sin escritores concurrentes. La reversión
adquiere el bloqueo de tabla antes de inspeccionar clasificación/multiplicidad
y lo mantiene en la transacción de migración para evitar carreras con DML.
No se borran identidades ni se reasignan documentos para restaurar OneToOne.
"""
import django.db.models.deletion
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError
from django.db.models import Count


def protect_reverse(apps, schema_editor):
    Supplier = apps.get_model("people", "Supplier")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("LOCK TABLE %s IN ACCESS EXCLUSIVE MODE" %
                       schema_editor.quote_name(Supplier._meta.db_table))
    rows = Supplier.objects.using(schema_editor.connection.alias)
    if rows.filter(company_id__isnull=False).exists():
        raise IrreversibleError("Supplier tiene clasificación empresarial; la reversión la perdería.")
    if rows.values("person_id").annotate(total=Count("pk")).filter(total__gt=1).exists():
        raise IrreversibleError("Una Person tiene varios Supplier; no puede restaurarse OneToOne sin pérdidas.")


class Migration(migrations.Migration):
    dependencies = [("people", "0005_customer_company_expansion")]

    operations = [
        migrations.AddField(
            model_name="supplier", name="company",
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.PROTECT, to="core.company"),
        ),
        migrations.AlterField(
            model_name="supplier", name="person",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="people.person"),
        ),
        migrations.AddConstraint(
            model_name="supplier",
            constraint=models.UniqueConstraint(fields=("company", "person"),
                                               name="people_supplier_company_person_unique"),
        ),
        # Primero en reversión; forward no ejecuta escrituras de datos.
        migrations.RunPython(migrations.RunPython.noop, protect_reverse),
    ]
