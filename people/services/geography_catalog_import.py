"""GEO-01: explicit geography-only ORM planning and atomic, approved execution."""
import copy
import hashlib
import json
import re
from collections import Counter

from django.db import connection, transaction

from people.models.geography import Continent, Country, Province, Canton, Parish
from people.services.geography_catalog_parser import analyze, equivalent_name

MODELS = (Continent, Country, Province, Canton, Parish)
PARENTS = {Country: 'continent', Province: 'country', Canton: 'province', Parish: 'canton'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def canonical_plan(value):
    """Normalize JSON sequences without dropping any plan fields."""
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))


def snapshots(*, lock=False):
    result = {}
    for model in MODELS:
        fields = ['id', 'name']
        if model is Country:
            fields.append('code')
        if model in PARENTS:
            fields.append(PARENTS[model] + '_id')
        queryset = model.objects.order_by('pk')
        if lock:
            queryset = queryset.select_for_update()
        result[model.__name__] = list(queryset.values(*fields))
    return result


def plan_import(rows, *, country_code=None, decisions=None, _snapshot=None):
    source = analyze(rows)
    snapshot = snapshots() if _snapshot is None else _snapshot
    effective_rows, resolution = rows, None
    if decisions is not None:
        from people.services.geography_import_decisions import resolve_decisions
        effective_rows, resolution = resolve_decisions(rows, decisions, snapshot)
    effective_source = analyze(effective_rows)
    conflicts, matches, nodes, cached = [], [], [], {}
    created, existing = Counter(), Counter()
    for field, model in (('province', Province), ('canton', Canton), ('parish', Parish)):
        limit = model._meta.get_field('name').max_length
        for row in effective_rows:
            if len(row[field]) > limit:
                conflicts.append({'kind': 'model_max_length', 'field': field, 'limit': limit, 'record': row})
    if country_code is not None and (not country_code.strip() or country_code != country_code.strip()
                                    or len(country_code) > Country._meta.get_field('code').max_length):
        conflicts.append({'kind': 'invalid_country_code', 'value': country_code})

    def resolve(model, name, parent=None):
        comparison = equivalent_name(name)
        key = (*parent['key'], model.__name__, comparison) if parent else (model.__name__, comparison)
        if key in cached:
            return cached[key]
        node = {'key': key, 'model': model, 'name': name, 'parent': parent,
                'existing_id': None, 'blocked': bool(parent and parent['blocked'])}
        cached[key] = node
        nodes.append(node)
        candidates = snapshot[model.__name__]
        if model in PARENTS:
            candidates = [x for x in candidates if parent['existing_id'] is not None
                          and x[PARENTS[model] + '_id'] == parent['existing_id']]
        found = [x for x in candidates if equivalent_name(x['name']) == comparison]
        if len(found) > 1:
            conflicts.append({'kind': 'ambiguous_existing_name', 'entity': model.__name__,
                              'name': name, 'parent': parent['key'] if parent else None,
                              'existing_names': [x['name'] for x in found]})
            node['blocked'] = True
        elif found:
            node['existing_id'] = found[0]['id']
            existing[model.__name__] += 1
            matches.append({'entity': model.__name__, 'source_name': name, 'existing_name': found[0]['name'],
                            'match': 'exact' if name == found[0]['name'] else 'equivalent',
                            'parent': parent['key'] if parent else None})
            if model is Country:
                node['code'] = found[0]['code']
                if country_code is not None and country_code != found[0]['code']:
                    conflicts.append({'kind': 'existing_country_code_mismatch', 'existing_code': found[0]['code'],
                                      'requested_code': country_code})
                    node['blocked'] = True
        elif not node['blocked']:
            base = equivalent_name(re.split(r'\s*\(', name, maxsplit=1)[0])
            possible = [x for x in candidates
                        if equivalent_name(re.split(r'\s*\(', x['name'], maxsplit=1)[0]) == base]
            if possible:
                conflicts.append({'kind': 'possible_existing_alias', 'entity': model.__name__, 'name': name,
                                  'existing_names': [x['name'] for x in possible], 'parent': parent['key'] if parent else None})
                node['blocked'] = True
            if model is Country:
                elsewhere = [x for x in snapshot['Country'] if equivalent_name(x['name']) == comparison]
                if elsewhere:
                    conflicts.append({'kind': 'country_parent_conflict', 'name': name})
                    node['blocked'] = True
                if country_code is None:
                    conflicts.append({'kind': 'country_code_required_for_creation'})
                    node['blocked'] = True
                elif any(x['code'] == country_code for x in snapshot['Country']):
                    conflicts.append({'kind': 'country_code_collision', 'requested_code': country_code})
                    node['blocked'] = True
                node['code'] = country_code
            if not node['blocked']:
                created[model.__name__] += 1
        return node

    continent = resolve(Continent, 'América')
    country = resolve(Country, 'Ecuador', continent)
    # Stable traversal: exact duplicate rows are processed once. Variant spellings
    # are reported by analyze() and prohibit application of the entire plan.
    unique = sorted({(r['province_code'], r['province'], r['canton'], r['parish']) for r in effective_rows})
    for code, province_name, canton_name, parish_name in unique:
        if not re.fullmatch(r'(0[1-9]|1[0-9]|2[0-4])', code):
            continue  # Kept in CSV/report as a blocker; never mapped to Province.
        province = resolve(Province, province_name, country)
        canton = resolve(Canton, canton_name, province)
        resolve(Parish, parish_name, canton)
    report = {'format': 'GEO-01/v1', 'dry_run': True,
              'database_name': str(connection.settings_dict['NAME']), 'database_vendor': connection.vendor, 'source_rows_sha256': digest(rows),
              'database_snapshot_sha256': digest(snapshot), 'requested_country_code': country_code,
              'source': source, 'would_create': {m.__name__: created[m.__name__] for m in MODELS},
              'existing': {m.__name__: existing[m.__name__] for m in MODELS},
              'matches': matches, 'conflicts': conflicts,
              'blocked': bool(conflicts or effective_source['ambiguities'] or effective_source['equivalent_names']
                              or effective_source['possible_typographical_variants']
                              or (resolution and resolution['pending_cases'])),
              'created': {m.__name__: 0 for m in MODELS}}
    if resolution is not None:
        report.update(format='GEO-01/v2', effective_source=effective_source, resolution=resolution)
    return report, nodes


@transaction.atomic
def apply_import(rows, approved_plan, *, country_code=None, decisions=None):
    # All catalog rows are locked in a fixed order. No operational table is read
    # or written. Unique Country.code also protects empty-database contention;
    # any collision aborts this whole transaction rather than leaving fragments.
    current, nodes = plan_import(rows, country_code=country_code, decisions=decisions, _snapshot=snapshots(lock=True))
    current_content = canonical_plan(current)
    approved_content = canonical_plan(approved_plan)
    if (current_content != approved_content
            or digest(current_content) != digest(approved_content)):
        raise ValueError('El CSV o la base han cambiado. Genere y apruebe un nuevo dry-run.')
    if current['blocked']:
        raise ValueError('El catálogo tiene conflictos o ambigüedades pendientes. No se ha importado.')
    objects = {}
    counts = Counter()
    for node in nodes:
        model = node['model']
        if node['existing_id'] is not None:
            instance = model.objects.get(pk=node['existing_id'])
        else:
            values = {'name': node['name']}
            if model in PARENTS:
                values[PARENTS[model]] = objects[node['parent']['key']]
            if model is Country:
                values['code'] = node['code']
            instance = model(**values)
            instance.full_clean()
            instance.save(force_insert=True)
            counts[model.__name__] += 1
        objects[node['key']] = instance
    return {**current, 'dry_run': False, 'created': {m.__name__: counts[m.__name__] for m in MODELS}}


def simulate_repeat(rows, *, country_code=None, decisions=None):
    """Project the eligible nodes in memory, then plan again; never save or delete."""
    before = snapshots()
    first, nodes = plan_import(rows, country_code=country_code, decisions=decisions, _snapshot=before)
    effective = first.get('effective_source', first['source'])
    if (first['conflicts'] or effective['ambiguities'] or effective['equivalent_names']
            or effective['possible_typographical_variants'] or any(n['blocked'] for n in nodes)):
        raise ValueError('No se puede simular un subconjunto que conserva conflictos de validación.')
    projected = copy.deepcopy(before)
    ids = {}
    next_ids = {name:max((r['id'] for r in records), default=0) + 1 for name, records in projected.items()}
    for node in nodes:
        model = node['model']
        name = model.__name__
        if node['existing_id'] is not None:
            ids[node['key']] = node['existing_id']
            continue
        pk = next_ids[name]
        next_ids[name] += 1
        record = {'id':pk,'name':node['name']}
        if model in PARENTS:
            record[PARENTS[model] + '_id'] = ids[node['parent']['key']]
        if model is Country:
            record['code'] = node['code']
        projected[name].append(record)
        ids[node['key']] = pk
    second, _ = plan_import(rows, country_code=country_code, decisions=decisions, _snapshot=projected)
    return {'kind':'memory_projection_only','actual_writes':0,
            'database_before_sha256':digest(before), 'projected_snapshot_sha256':digest(projected),
            'first_would_create':first['would_create'], 'second_would_create':second['would_create'],
            'second_existing':second['existing'], 'second_blocked':second['blocked'],
            'idempotent':not any(second['would_create'].values()),
            'projected_database_counts':{name:len(records) for name,records in projected.items()}}
