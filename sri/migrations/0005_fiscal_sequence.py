import re

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Count


def preflight_and_backfill(apps, schema_editor):
    alias = schema_editor.connection.alias
    documents = apps.get_model('sri', 'ElectronicDocument').objects.using(alias)
    counters = apps.get_model('sri', 'FiscalSequence').objects.using(alias)
    if counters.exists():
        raise RuntimeError('FiscalSequence preexistente: se requiere revisión explícita.')
    duplicate = (documents.order_by().values('content_type_id', 'object_id')
                 .annotate(count=Count('id')).filter(count__gt=1)
                 .order_by('content_type_id', 'object_id').first())
    if duplicate:
        raise RuntimeError(f'Origen electrónico duplicado: {duplicate}')

    maxima = {}
    for row in documents.order_by().values(
        'id', 'company_id', 'establishment', 'emission_point', 'document_type', 'sequential',
    ).iterator():
        for field, width in (('establishment', 3), ('emission_point', 3),
                             ('document_type', 2), ('sequential', 9)):
            value = row[field]
            if not isinstance(value, str) or re.fullmatch(r'[0-9]{%d}' % width, value) is None:
                raise RuntimeError(f'Historia fiscal inválida: id={row["id"]}, campo={field}.')
        number = int(row['sequential'])
        if not 1 <= number <= 999999999:
            raise RuntimeError(f'Secuencial histórico fuera de rango: id={row["id"]}.')
        scope = tuple(row[field] for field in (
            'company_id', 'establishment', 'emission_point', 'document_type',
        ))
        maxima[scope] = max(maxima.get(scope, 0), number)

    # Only write after validating the entire history. All statuses/environments count.
    for (company_id, establishment, emission_point, document_type), maximum in maxima.items():
        counters.create(
            company_id=company_id, establishment=establishment,
            emission_point=emission_point, document_type=document_type,
            next_number=maximum + 1,
        )


class Migration(migrations.Migration):
    atomic = True
    dependencies = [('sri', '0004_sricertificate')]
    operations = [
        migrations.CreateModel(
            name='FiscalSequence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='core.company')),
                ('establishment', models.CharField(max_length=3)),
                ('emission_point', models.CharField(max_length=3)),
                ('document_type', models.CharField(max_length=2)),
                ('next_number', models.PositiveIntegerField(default=1)),
            ],
            options={'constraints': [
                models.UniqueConstraint(
                    fields=('company', 'establishment', 'emission_point', 'document_type'),
                    name='unique_sri_fiscal_sequence_scope',
                ),
                models.CheckConstraint(
                    condition=models.Q(next_number__gte=1, next_number__lte=1000000000),
                    name='sri_fiscal_sequence_next_range',
                ),
                models.CheckConstraint(
                    condition=models.Q(establishment__regex=r'\A[0-9]{3}\Z',
                                       emission_point__regex=r'\A[0-9]{3}\Z',
                                       document_type__regex=r'\A[0-9]{2}\Z'),
                    name='sri_fiscal_sequence_codes_valid',
                ),
            ]},
        ),
        # Intentionally irreversible: dropping consumed counters can reuse numbers.
        migrations.RunPython(preflight_and_backfill),
        migrations.AddConstraint(
            model_name='electronicdocument',
            constraint=models.UniqueConstraint(
                fields=('content_type', 'object_id'),
                name='unique_sri_electronic_document_origin',
            ),
        ),
    ]
