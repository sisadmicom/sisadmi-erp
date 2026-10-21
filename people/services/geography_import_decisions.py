"""Source-bound GEO-01 decisions; every original row keeps its provenance."""
import copy
import hashlib
import json
import re
from collections import defaultdict

from people.services.geography_catalog_parser import equivalent_name

FIELDS = ('province_code', 'province', 'canton', 'parish')


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _existing_context(target, snapshot):
    if not isinstance(target, dict) or not isinstance(target.get('parish'), dict):
        raise ValueError('Falta la identidad del registro que se desea reutilizar.')
    for name in ('continent','country','province','canton','parish'):
        part = target.get(name)
        if not isinstance(part, dict) or type(part.get('id')) is not int or part['id'] <= 0:
            raise ValueError('La identidad existente debe declarar cada registro de su cadena geográfica.')
    tables = {name: {row['id']: row for row in records} for name, records in snapshot.items()}
    try:
        parish = tables['Parish'][target['parish']['id']]
        canton = tables['Canton'][parish['canton_id']]
        province = tables['Province'][canton['province_id']]
        country = tables['Country'][province['country_id']]
        continent = tables['Continent'][country['continent_id']]
    except (KeyError, TypeError):
        raise ValueError('El registro para reutilizar o su ubicación ya no están disponibles.') from None
    actual = {name: {'id': row['id'], 'name': row['name']}
              for name, row in (('continent',continent),('country',country),('province',province),
                                ('canton',canton),('parish',parish))}
    actual['country']['code'] = country['code']
    if actual != target:
        raise ValueError('La identidad o la ubicación del registro para reutilizar han cambiado.')
    if equivalent_name(continent['name']) != 'america' or equivalent_name(country['name']) != 'ecuador':
        raise ValueError('La reutilización debe pertenecer a América y Ecuador.')
    return actual


def resolve_decisions(rows, manifest, snapshot):
    if not isinstance(manifest, dict) or manifest.get('format') != 'GEO-01/decisions-v1':
        raise ValueError('El archivo de decisiones no tiene el formato GEO-01 esperado.')
    if manifest.get('source_rows_sha256') != _digest(rows):
        raise ValueError('Las decisiones no corresponden a las filas originales del CSV.')
    if manifest.get('exact_duplicates') != 'consolidate_preserve_references':
        raise ValueError('Debe declararse la consolidación trazable de duplicados exactos.')
    choices = manifest.get('decisions')
    if not isinstance(choices, list):
        raise ValueError('Falta la lista explícita de decisiones.')
    refs, originals = {}, defaultdict(list)
    for row in rows:
        ref = (row['source_page'], row['source_row'])
        if ref in refs:
            raise ValueError('Dos filas declaran la misma página y fila de origen.')
        refs[ref] = row
        originals[tuple(row[field] for field in FIELDS)].append(copy.deepcopy(row))
    replacements, review, assigned = {}, {}, {}
    verified, pending, ids = [], [], set()
    equivalent_consolidated = 0
    for choice in choices:
        if not isinstance(choice, dict) or not isinstance(choice.get('id'), str) or not choice['id'] or choice['id'] in ids:
            raise ValueError('Las decisiones deben tener identificadores únicos.')
        ids.add(choice['id'])
        if not isinstance(choice.get('evidence'), str) or not choice['evidence'].strip():
            raise ValueError('Cada decisión debe conservar su evidencia o motivo de revisión.')
        locations = choice.get('rows')
        if not isinstance(locations, list) or not locations or not all(isinstance(r, dict) for r in locations):
            raise ValueError('Cada decisión debe referenciar filas originales.')
        locations = [(str(r.get('page')), str(r.get('row'))) for r in locations]
        if len(set(locations)) != len(locations) or any(ref not in refs for ref in locations):
            raise ValueError('Una decisión referencia filas inexistentes o repetidas.')
        records = [refs[ref] for ref in locations]
        keys = {tuple(row[field] for field in FIELDS) for row in records}
        if any(key in assigned for key in keys):
            raise ValueError('Una fila original tiene decisiones incompatibles o superpuestas.')
        action = choice.get('action')
        if action == 'review':
            if choice.get('status', 'pending') != 'pending':
                raise ValueError('Una revisión pendiente no puede declararse resuelta por omisión.')
            for key in keys:
                review[key] = choice['id']
            pending.append(copy.deepcopy(choice))
        elif action == 'equivalent':
            parents = {key[:3] for key in keys}
            names = {key[3] for key in keys}
            canonical = choice.get('canonical_name')
            if len(keys) < 2 or len(parents) != 1 or not isinstance(canonical, str) or canonical not in names or len({equivalent_name(n) for n in names}) != 1:
                raise ValueError('La equivalencia requiere el mismo código, provincia, cantón y una grafía ya presente.')
            for key in keys:
                replacements[key] = canonical
            equivalent_consolidated += len(keys) - 1
            verified.append(copy.deepcopy(choice))
        elif action == 'reuse_existing':
            if len(keys) != 1:
                raise ValueError('La reutilización debe identificar una sola identidad original.')
            actual = _existing_context(choice.get('target'), snapshot)
            key = next(iter(keys))
            base = re.split(r'\s*\(', key[3], maxsplit=1)[0]
            if (equivalent_name(key[1]) != equivalent_name(actual['province']['name'])
                    or equivalent_name(key[2]) != equivalent_name(actual['canton']['name'])
                    or equivalent_name(base) != equivalent_name(actual['parish']['name'])):
                raise ValueError('El nombre, provincia o cantón no confirman la reutilización seleccionada.')
            replacements[key] = actual['parish']['name']
            verified.append(copy.deepcopy(choice))
        else:
            raise ValueError('La acción de decisión no está admitida para GEO-01.')
        for key in keys:
            assigned[key] = choice['id']

    groups, held = {}, []
    for key, source_rows in originals.items():
        if key in review:
            held.append({'status':'review','effective':None,'decision_ids':[review[key]],
                         'source_rows':source_rows})
            continue
        effective_key = (*key[:3], replacements.get(key, key[3]))
        if effective_key not in groups:
            representative = copy.deepcopy(source_rows[0])
            representative['parish'] = effective_key[3]
            groups[effective_key] = {'status':'eligible','effective':representative,
                                    'decision_ids':[], 'source_rows':[]}
        group = groups[effective_key]
        group['source_rows'].extend(source_rows)
        if key in assigned and assigned[key] not in group['decision_ids']:
            group['decision_ids'].append(assigned[key])
    eligible = [g['effective'] for g in groups.values()]
    lineage = [*groups.values(), *held]
    counts = {'source_rows':len(rows),'unique_original_rows':len(originals),
              'exact_duplicate_rows_consolidated':len(rows)-len(originals),
              'equivalent_rows_consolidated':equivalent_consolidated,
              'alias_rows_consolidated':len(originals)-len(review)-len(groups)-equivalent_consolidated,
              'excluded_source_rows':sum(len(g['source_rows']) for g in held),
              'excluded_distinct_rows':len(held), 'eligible_distinct_rows':len(eligible),
              'pending_cases':len(pending)}
    return eligible, {'decisions_sha256':_digest(manifest),'counts':counts,
                      'verified_decisions':verified,'pending_cases':pending,'lineage':lineage}
