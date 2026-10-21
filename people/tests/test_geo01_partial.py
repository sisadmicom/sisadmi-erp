"""Approved partial catalog: complete provenance, retained parents, no writes."""
import json
from pathlib import Path
from django.test import SimpleTestCase
from people.services.geography_catalog_parser import read_csv, sha256

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/geo01'


class Geo01PartialTests(SimpleTestCase):
    def test_subset_excludes_only_review_and_preserves_approved_names_and_parents(self):
        source = read_csv(DATA/'ecuador_2016.csv')
        subset = read_csv(DATA/'phase2/ecuador_2016_partial.csv')
        lineage = json.loads((DATA/'phase2/lineage.json').read_text())
        held = [g for g in lineage if g['status']=='review']
        self.assertEqual(sum(len(g['source_rows']) for g in held), 11)
        self.assertEqual(len(subset),1354)
        self.assertEqual(subset,[g['effective'] for g in lineage if g['status']=='eligible'])
        refs = [(r['source_page'],r['source_row']) for g in lineage for r in g['source_rows']]
        self.assertCountEqual(refs,[(r['source_page'],r['source_row']) for r in source])
        valid=[r for r in source if r['province_code']!='90']
        for fields in (('province_code','province'),('province_code','province','canton')):
            self.assertEqual({tuple(r[f] for f in fields) for r in valid},
                             {tuple(r[f] for f in fields) for r in subset})
        names={(r['province'],r['canton'],r['parish']) for r in subset}
        for path in [('CARCHI','ESPEJO','EL ÁNGEL'),('PICHINCHA','RUMIÑAHUI','SANGOLQUÍ'),
                     ('MANABI','PORTOVIEJO','RIOCHICO')]:
            self.assertIn(path,names)

    def test_projected_operations_and_repeat_have_exact_counts(self):
        report=json.loads((DATA/'phase2/dry_run.json').read_text())
        operations=json.loads((DATA/'phase2/operations.json').read_text())
        repeat=json.loads((DATA/'phase2/repeat_simulation.json').read_text())
        self.assertFalse(report['blocked'])
        self.assertEqual(report['would_create'],dict(Continent=0,Country=0,Province=23,Canton=220,Parish=1353))
        self.assertEqual({op:sum(r['operation']==op for r in operations)
                          for op in ('CREATE','REUSE','SKIP','CONFLICT')},
                         dict(CREATE=1596,REUSE=5,SKIP=44,CONFLICT=0))
        self.assertEqual(sum(repeat['second_would_create'].values()),0)
        self.assertTrue(repeat['idempotent'])
        self.assertEqual(repeat['actual_writes'],0)

    def test_preserved_artifacts_and_database_audit(self):
        audit=json.loads((DATA/'phase2/verification.json').read_text())
        self.assertEqual(audit['database_name'],'sisadmi_erp_dev')
        self.assertEqual(audit['database_before'],audit['database_after'])
        self.assertFalse(audit['execution_authorized'])
        self.assertEqual(audit['actual_database_writes'],0)
        for path,expected in audit['protected_artifact_hashes'].items():
            self.assertEqual(sha256(ROOT/path),expected,path)
        self.assertEqual(sha256(DATA/'phase2/ecuador_2016_partial.csv'),audit['subset_sha256'])
