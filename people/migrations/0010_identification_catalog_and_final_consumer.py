"""Proposed data initialization. Review TEST conflicts BEFORE applying."""
from django.db import migrations

KINDS = (('CEDULA', 'Cédula'), ('RUC', 'RUC'), ('PASSPORT', 'Pasaporte'),
         ('FOREIGN_ID', 'Identificación del exterior (histórico)'), ('OTHER', 'Otro'),
         ('FINAL_CONSUMER', 'Consumidor Final'))


def initialize(apps, schema_editor):
    alias = schema_editor.connection.alias
    Person = apps.get_model('people', 'Person')
    Kind = apps.get_model('people', 'IdentificationKind')
    Company = apps.get_model('core', 'Company')
    Access = apps.get_model('people', 'CompanyPersonAccess')
    Customer = apps.get_model('people', 'Customer')
    # Do not adopt, rename or reclassify any preexisting reserved identity.
    if Person.objects.using(alias).filter(identification='9999999999999').exists():
        raise RuntimeError('Identificación reservada existente: requiere decisión funcional antes de migrar.')
    for code, name in KINDS:
        Kind.objects.using(alias).get_or_create(code=code, defaults={'name': name})
    kind = Kind.objects.using(alias).get(code='FINAL_CONSUMER')
    person = Person.objects.using(alias).create(identification='9999999999999',
        identification_type='FINAL_CONSUMER', identification_kind=kind,
        person_type='NATURAL', full_name='CONSUMIDOR FINAL')
    for company in Company.objects.using(alias).order_by('pk').iterator():
        Access.objects.using(alias).get_or_create(company=company, person=person)
        Customer.objects.using(alias).get_or_create(company=company, person=person)


class Migration(migrations.Migration):
    dependencies = [('people', '0009_alter_person_identification_type_identificationkind_and_more')]
    operations = [migrations.RunPython(initialize)]
