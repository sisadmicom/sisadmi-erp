"""Reproducible extraction of the four columns in the GEO-01 source PDF."""
import csv
import hashlib
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from itertools import combinations
from xml.etree import ElementTree

COLUMNS = ('province_code', 'province', 'canton', 'parish', 'source_page', 'source_row')
NS = {'x': 'http://www.w3.org/1999/xhtml'}


def equivalent_name(name):
    # Used only for detection/matching; the original spelling is never rewritten.
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', name.casefold())
                           if not unicodedata.combining(c)).split())


def parse_bbox(xml):
    root = ElementTree.fromstring(xml)
    rows = []
    for page_number, page in enumerate(root.findall('.//x:page', NS), 1):
        words = [(w.text or '', float(w.attrib['xMin']), float(w.attrib['xMax']),
                  float(w.attrib['yMin'])) for w in page.findall('.//x:word', NS)]
        anchors = sorted((w for w in words if re.fullmatch(r'\d{2}', w[0])
                          and 70 < (w[1] + w[2]) / 2 < 100), key=lambda w: w[3])
        lines = []
        for line in page.findall('.//x:line', NS):
            tokens = [(w.text or '', float(w.attrib['xMin']), float(w.attrib['xMax']))
                      for w in line.findall('x:word', NS)]
            if tokens:
                lines.append((float(line.attrib['xMin']), float(line.attrib['yMin']), tokens))
        for row_number, anchor in enumerate(anchors, 1):
            aligned = sorted((line for line in lines if abs(line[1] - anchor[3]) <= 2),
                             key=lambda line: line[0])
            if len(aligned) == 4:
                cells = [' '.join(t[0] for t in line[2]) for line in aligned]
            elif len(aligned) == 3:
                # Poppler merged adjacent canton/parish text into one line.
                # Only split at a clearly separated gap between those cells.
                tokens = aligned[2][2]
                gaps = [(tokens[i][1] - tokens[i-1][2], i) for i in range(1, len(tokens))
                        if 300 <= (tokens[i][1] + tokens[i-1][2]) / 2 <= 360]
                gap, cut = max(gaps, default=(0, 0))
                if gap < 5:
                    raise ValueError(f'Columnas ambiguas en página {page_number}, fila {row_number}.')
                cells = [' '.join(t[0] for t in line[2]) for line in aligned[:2]]
                cells += [' '.join(t[0] for t in tokens[:cut]), ' '.join(t[0] for t in tokens[cut:])]
            else:
                raise ValueError(f'Fila incompleta en página {page_number}, fila {row_number}.')
            if cells[0] != anchor[0]:
                raise ValueError(f'Código ambiguo en página {page_number}, fila {row_number}.')
            rows.append(dict(zip(COLUMNS, [*cells, str(page_number), str(row_number)])))
    if not rows:
        raise ValueError('No se encontraron filas geográficas en el PDF.')
    return rows


def extract_pdf(path):
    result = subprocess.run(['pdftotext', '-bbox-layout', str(path), '-'],
                            check=True, capture_output=True)
    return parse_bbox(result.stdout)


def write_csv(rows, path):
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    try:
        with Path(path).open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream, strict=True)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                raise ValueError('El CSV no tiene las columnas GEO-01 esperadas.')
            rows = list(reader)
    except csv.Error as exc:
        raise ValueError('El CSV contiene una estructura inválida: ' + str(exc)) from exc
    if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError('El CSV está vacío o contiene columnas incompletas.')
    return rows


def one_edit_apart(left, right):
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    if len(left) > len(right):
        left, right = right, left
    return any(left == right[:i] + right[i+1:] for i in range(len(right)))


def analyze(rows):
    duplicates, equivalents, issues = [], [], []
    by_key, names, codes = defaultdict(list), defaultdict(set), defaultdict(set)
    for row in rows:
        key = tuple(row[k] for k in COLUMNS[:4])
        by_key[key].append({'page': row['source_page'], 'row': row['source_row']})
        codes[row['province_code']].add(row['province'])
        for index, field in enumerate(COLUMNS[1:4], 1):
            value = row[field]
            parent = tuple(row[k] for k in COLUMNS[:index])
            names[(field, parent, equivalent_name(value))].add(value)
            if not value.strip() or value != value.strip() or any(ord(c) < 32 for c in value):
                issues.append({'kind': 'incomplete_or_invalid_name', 'field': field, 'record': row})
            if value.count('(') != value.count(')'):
                issues.append({'kind': 'unbalanced_parentheses', 'field': field, 'record': row})
        if not re.fullmatch(r'(0[1-9]|1[0-9]|2[0-4])', row['province_code']):
            issues.append({'kind': 'non_province_code', 'record': row})
        for field in ('source_page', 'source_row'):
            if not row[field].isdigit() or int(row[field]) < 1:
                issues.append({'kind': 'invalid_source_reference', 'field': field, 'record': row})
    for key, references in by_key.items():
        if len(references) > 1:
            duplicates.append({'values': dict(zip(COLUMNS[:4], key)), 'references': references,
                               'extra_rows': len(references) - 1})
    for (field, parent, normalized), values in names.items():
        if len(values) > 1:
            equivalents.append({'field': field, 'parent': parent, 'comparison': normalized,
                                'names': sorted(values)})
    for code, values in codes.items():
        if len(values) != 1:
            issues.append({'kind': 'province_code_has_multiple_names', 'code': code, 'names': sorted(values)})
    name_codes = defaultdict(set)
    for code, values in codes.items():
        for name in values:
            name_codes[equivalent_name(name)].add(code)
    for name, values in name_codes.items():
        if len(values) != 1:
            issues.append({'kind': 'province_name_has_multiple_codes', 'name': name, 'codes': sorted(values)})
    parish_groups = defaultdict(set)
    for row in rows:
        parish_groups[(row['province_code'], row['province'], row['canton'])].add(row['parish'])
    typographical = []
    for parent, values in sorted(parish_groups.items()):
        for left, right in combinations(sorted(values), 2):
            a, b = equivalent_name(left), equivalent_name(right)
            if min(len(a), len(b)) >= 6 and one_edit_apart(a, b):
                typographical.append({'parent': parent, 'names': [left, right]})
    counts = Counter((r['province_code'], r['province'], r['canton'])
                     for r in {tuple(row[k] for k in COLUMNS[:4]): row for row in rows}.values())
    return {'rows': len(rows), 'distinct_rows': len(by_key),
            'provinces': [{'code': c, 'names': sorted(n)} for c, n in sorted(codes.items())],
            'distinct_cantons': len(counts),
            'parishes_by_canton': [{'province_code': k[0], 'province': k[1], 'canton': k[2],
                                   'distinct_parishes': v} for k, v in sorted(counts.items())],
            'duplicates': duplicates, 'duplicate_extra_rows': sum(d['extra_rows'] for d in duplicates),
            'equivalent_names': equivalents, 'possible_typographical_variants': typographical, 'ambiguities': issues}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
