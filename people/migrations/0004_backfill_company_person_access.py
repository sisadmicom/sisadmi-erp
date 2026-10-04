"""Seed only the unequivocal legal Person of each existing Company.

Irreversible: association provenance is not stored, so reversal cannot safely
distinguish a backfilled association from one explicitly authorized later.
"""

from django.db import migrations


def backfill_company_person_access(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    CompanyPersonAccess = apps.get_model("people", "CompanyPersonAccess")
    alias = schema_editor.connection.alias
    companies = Company.objects.using(alias).order_by("pk").values_list("pk", "person_id")
    for company_id, person_id in companies.iterator():
        CompanyPersonAccess.objects.using(alias).get_or_create(
            company_id=company_id, person_id=person_id
        )


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0003_companypersonaccess"),
    ]

    operations = [
        migrations.RunPython(backfill_company_person_access),
    ]
