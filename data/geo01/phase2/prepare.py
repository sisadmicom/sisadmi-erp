"""Reproduce GEO-01 phase 2 artifacts. Read-only ORM and dry-run only."""
import json
from pathlib import Path

from django.core.management import call_command
from people.services.geography_catalog_import import digest, snapshots, plan_import
from people.services.geography_catalog_parser import read_csv, write_csv, sha256
from people.services.geography_import_decisions import resolve_decisions

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def main():
    original = ROOT / 'data/geo01'
    phase1 = original / 'phase1'
    protected = {str(p.relative_to(ROOT)): sha256(p)
                 for p in original.rglob('*') if p.is_file() and OUT not in p.parents}
    baseline = json.loads((phase1 / 'database_before.json').read_text())
    before = snapshots()
    if digest(before) != baseline['snapshot_sha256']:
        raise ValueError('La base geográfica cambió respecto al plan aprobado; detener.')
    rows = read_csv(original / 'ecuador_2016.csv')
    choices = json.loads((phase1 / 'import_decisions.json').read_text())
    if sha256(original / 'ecuador_2016.csv') != choices['source_csv_sha256']:
        raise ValueError('CSV original alterado.')
    approved = json.loads((phase1 / 'development_plan.json').read_text())
    eligible, resolution = resolve_decisions(rows, choices, before)
    if resolution != approved['resolution']:
        raise ValueError('Las decisiones o su trazabilidad difieren del plan aprobado.')
    stats = resolution['counts']
    if (stats['pending_cases'], stats['excluded_source_rows'], len(eligible)) != (10, 11, 1354):
        raise ValueError('Exclusiones o cantidad de filas inesperadas.')
    valid = [r for r in rows if r['province_code'] in {f'{i:02}' for i in range(1,25)}]
    parents = lambda rs: ({(r['province_code'], r['province']) for r in rs},
                          {(r['province_code'], r['province'], r['canton']) for r in rs})
    if parents(valid) != parents(eligible):
        raise ValueError('La exclusión pierde provincias o cantones válidos.')
    report, nodes = plan_import(eligible)
    expected = {'Continent':0,'Country':0,'Province':23,'Canton':220,'Parish':1353}
    if report['blocked'] or report['conflicts'] or report['would_create'] != expected:
        raise ValueError('Conflictos adicionales o cantidades inesperadas; detener.')
    write_csv(eligible, OUT / 'ecuador_2016_partial.csv')
    call_command('import_ecuador_geography', csv=str(OUT/'ecuador_2016_partial.csv'),
                 dry_run=True, simulate_repeat=True, report=str(OUT/'dry_run.json'),
                 simulation_report=str(OUT/'repeat_simulation.json'))
    operations = []
    for node in nodes:
        operations.append({'operation':'REUSE' if node['existing_id'] else 'CREATE',
                           'entity':node['model'].__name__, 'name':node['name'],
                           'existing_id':node['existing_id'], 'path':list(node['key'])})
    for group in resolution['lineage']:
        for n, row in enumerate(group['source_rows']):
            if group['status'] == 'review' or n:
                operations.append({'operation':'SKIP','entity':'SourceRow',
                    'reason':'pending_review' if group['status']=='review' else 'consolidated',
                    'decision_ids':group['decision_ids'], 'source':row})
    def save(name, value):
        (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    save('operations.json', operations)
    save('lineage.json', resolution['lineage'])
    save('pending_exceptions.json', resolution['pending_cases'])
    simulation = json.loads((OUT/'repeat_simulation.json').read_text())
    if not simulation['idempotent'] or simulation['second_blocked']:
        raise ValueError('La simulación de segunda ejecución no es válida.')
    after = snapshots()
    if before != after or any(sha256(ROOT/p) != h for p,h in protected.items()):
        raise ValueError('La base o los artefactos originales cambiaron; detener.')
    save('verification.json', {'execution_authorized':False, 'actual_database_writes':0,
        'database_name':report['database_name'], 'database_before':before,'database_after':after,
        'database_sha256':digest(after),'protected_artifact_hashes':protected,
        'subset_sha256':sha256(OUT/'ecuador_2016_partial.csv'),
        'parent_counts':{'provinces':len(parents(eligible)[0]),'cantons':len(parents(eligible)[1])},
        'source_counts':stats, 'operations':{op:sum(r['operation']==op for r in operations)
                                            for op in ('CREATE','REUSE','SKIP','CONFLICT')}})


if __name__ == '__main__':
    main()
