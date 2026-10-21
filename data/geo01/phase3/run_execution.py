"""Authorized GEO-01 execution: guarded database, backup, ORM APPLY and audit."""
import json
from datetime import datetime, timezone
from pathlib import Path
from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management import call_command
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from people.services.geography_catalog_import import MODELS, PARENTS, snapshots, digest, canonical_plan
from people.services.geography_catalog_parser import read_csv, sha256

ROOT = Path.cwd()
OUT = ROOT/'data/geo01/phase3'
PARTIAL = ROOT/'data/geo01/phase2'
EXPECTED_NEW = dict(Continent=0,Country=0,Province=23,Canton=220,Parish=1353)
EXPECTED_FINAL = dict(Continent=1,Country=1,Province=24,Canton=221,Parish=1355)

def save(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder)+'\n', encoding='utf-8')

def business_audit():
    result = {}
    for model in apps.get_models(include_auto_created=True):
        if model in MODELS or model._meta.proxy:
            continue
        records = list(model.objects.order_by(model._meta.pk.name).values())
        normalized = json.loads(json.dumps(records, ensure_ascii=False, cls=DjangoJSONEncoder))
        result[model._meta.label] = {'count':len(records),'sha256':digest(normalized)}
    return result

def assert_relationships(after):
    for child, parent_field in PARENTS.items():
        parent = child._meta.get_field(parent_field).remote_field.model
        ids = {row['id'] for row in after[parent.__name__]}
        assert all(row[parent_field+'_id'] in ids for row in after[child.__name__])
    assert {r['country_id'] for r in after['Province']} == {1}
    assert {r['continent_id'] for r in after['Country']} == {1}

def main():
    assert connection.vendor == 'postgresql'
    assert connection.settings_dict['NAME'] == 'sisadmi_erp_dev'
    assert settings.DEBUG is True
    assert not (OUT/'execution_report.json').exists(), 'Execution already recorded; do not repeat APPLY.'
    approved_audit = json.loads((PARTIAL/'verification.json').read_text())
    assert snapshots() == approved_audit['database_before']
    assert sum(map(len,snapshots().values())) == 6
    assert sha256(PARTIAL/'ecuador_2016_partial.csv') == approved_audit['subset_sha256']
    assert all(sha256(ROOT/name)==value for name,value in approved_audit['protected_artifact_hashes'].items())
    protected = {str(p.relative_to(ROOT)):sha256(p)
                 for p in (ROOT/'data/geo01').rglob('*')
                 if p.is_file() and OUT not in p.parents}
    before = snapshots()
    business_before = business_audit()
    save('before_audit.json', {'geography':before,'business':business_before,'protected_hashes':protected})
    objects = [obj for model in MODELS for obj in model.objects.order_by('pk')]
    backup = OUT/'geography_backup.json'
    backup.write_text(serializers.serialize('json',objects,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    restored = [entry.object for entry in serializers.deserialize('json',backup.read_text())]
    assert len(restored)==6
    for obj, original in zip(restored,objects):
        assert type(obj) is type(original)
        assert all(getattr(obj,f.attname)==getattr(original,f.attname) for f in obj._meta.concrete_fields)
    save('backup_manifest.json', {'database':'sisadmi_erp_dev','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'file':str(backup.relative_to(ROOT)),'sha256':sha256(backup),'records':6,
        'serialization_roundtrip_verified':True,'format':'Django JSON fixture',
        'recovery':'manage.py loaddata geography_backup.json in an explicitly authorized recovery target; never run automatically'})
    call_command('import_ecuador_geography',csv=str(PARTIAL/'ecuador_2016_partial.csv'),dry_run=True,
                 report=str(OUT/'pre_execution_dry_run.json'))
    dry = json.loads((OUT/'pre_execution_dry_run.json').read_text())
    approved = json.loads((PARTIAL/'dry_run.json').read_text())
    assert dry==approved
    assert dry['would_create']==EXPECTED_NEW and sum(dry['existing'].values())==5
    assert not dry['conflicts'] and not dry['blocked']
    committed = False
    try:
        with transaction.atomic():
            assert snapshots(lock=True)==before
            assert business_audit()==business_before
            call_command('import_ecuador_geography', csv=str(PARTIAL/'ecuador_2016_partial.csv'),apply=True,
                         approved_plan=str(PARTIAL/'dry_run.json'),report=str(OUT/'apply_result.json'))
            result = json.loads((OUT/'apply_result.json').read_text())
            assert result['created']==EXPECTED_NEW
            after = snapshots()
            assert {name:len(records) for name,records in after.items()}==EXPECTED_FINAL
            assert_relationships(after)
            for name, originals in before.items():
                by_id = {r['id']:r for r in after[name]}
                assert all(by_id[r['id']]==r for r in originals)
            assert business_audit()==business_before
            assert all(sha256(ROOT/name)==value for name,value in protected.items())
        committed = True
        call_command('import_ecuador_geography',csv=str(PARTIAL/'ecuador_2016_partial.csv'),dry_run=True,
                     report=str(OUT/'second_dry_run.json'))
        second = json.loads((OUT/'second_dry_run.json').read_text())
        assert not any(second['would_create'].values()) and not second['blocked']
        assert business_audit()==business_before
        save('execution_report.json', {'status':'COMMITTED_AND_VERIFIED','database':str(connection.settings_dict['NAME']),
            'vendor':connection.vendor,'development_debug':settings.DEBUG,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
            'backup_file':str(backup.relative_to(ROOT)),'backup_sha256':sha256(backup),
            'created':result['created'],'reused':result['existing'],'conflicts':result['conflicts'],
            'final_counts':EXPECTED_FINAL,'total_geographic_records':sum(EXPECTED_FINAL.values()),
            'original_six_intact':True,'hierarchy_validated':True,'business_data_unchanged':True,
            'all_non_geographic_model_digests':business_before,'approved_artifacts_unchanged':True,
            'second_dry_run_create':second['would_create'],'tests':'pending','system_gates':'pending'})
        print('IMPORT COMMITTED AND VERIFIED: 1596 CREATE, 5 REUSE; final total 1602')
    except Exception as exc:
        save('execution_error.json',{'error':str(exc),'committed':committed,'rolled_back':not committed,
                                    'timestamp_utc':datetime.now(timezone.utc).isoformat()})
        raise

if __name__=='__main__':
    main()
