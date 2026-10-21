"""Schema expansion only: no company inference and no data backfill.

Legacy rows remain pending (company NULL). A later, separately approved
classification/closure step must handle unresolved and ambiguous evidence.
Reverse is safe only while the original global identity is representable;
otherwise reject BEFORE dropping constraints/columns or changing data.
"""
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError
from django.db.models import Count
import django.db.models.deletion


def protect_reverse(apps, schema_editor):
    Customer = apps.get_model("people", "Customer")
    rows = Customer.objects.using(schema_editor.connection.alias)
    if rows.filter(company_id__isnull=False).exists():
        raise IrreversibleError("Customer tiene asignaciones empresariales; la reversión perdería esa clasificación.")
    if rows.values("person_id").annotate(total=Count("pk")).filter(total__gt=1).exists():
        raise IrreversibleError("Una Person tiene varios Customer; no puede restaurarse OneToOne sin perder identidades.")


class Migration(migrations.Migration):
    dependencies = [("people", "0004_backfill_company_person_access")]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="company",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    to="core.company"),
        ),
        migrations.AlterField(
            model_name="customer",
            name="person",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="people.person"),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(fields=("company", "person"),
                                               name="people_customer_company_person_unique"),
        ),
        # Reversal runs this protection first; forward performs no data writes.
        migrations.RunPython(migrations.RunPython.noop, protect_reverse),
    ]
