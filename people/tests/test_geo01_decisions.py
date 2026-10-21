"""Phase 1: explicit, scoped decisions and a write-free repeat simulation."""
import copy
import io
import json
import tempfile
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from people.models.geography import Continent, Country, Province, Canton, Parish
from people.services.geography_catalog_import import plan_import, apply_import, digest, simulate_repeat
from people.services.geography_catalog_parser import write_csv, sha256


def row(name, n, *, province='MANABI', code='13', canton='PORTOVIEJO'):
    return {'province_code':code,'province':province,'canton':canton,'parish':name,
            'source_page':'1','source_row':str(n)}


def decision(kind, refs, **values):
    return {'id':kind+'-'+str(refs[0]),'action':kind,'rows':[{'page':'1','row':str(n)} for n in refs],
            'evidence':'Source and parent context checked',**values}


def manifest(rows, decisions):
    return {'format':'GEO-01/decisions-v1','source_rows_sha256':digest(rows),
            'exact_duplicates':'consolidate_preserve_references','decisions':decisions}


class Geo01DecisionTests(TestCase):
    def setUp(self):
        self.continent=Continent.objects.create(name='America')
        self.country=Country.objects.create(name='ECUADOR',code='593',continent=self.continent)
        self.province=Province.objects.create(name='MANABI',country=self.country)
        self.canton=Canton.objects.create(name='PORTOVIEJO',province=self.province)
        self.parish=Parish.objects.create(name='RIOCHICO',canton=self.canton)
        self.other=Parish.objects.create(name='SAN ALEJO',canton=self.canton)
        self.target={'continent':{'id':self.continent.pk,'name':'America'},
                     'country':{'id':self.country.pk,'name':'ECUADOR','code':'593'},
                     'province':{'id':self.province.pk,'name':'MANABI'},
                     'canton':{'id':self.canton.pk,'name':'PORTOVIEJO'},
                     'parish':{'id':self.parish.pk,'name':'RIOCHICO'}}

    def test_consolidation_has_complete_source_lineage_and_keeps_names(self):
        rows=[row('EL ÁNGEL',1,province='CARCHI',code='04',canton='ESPEJO'),
              row('EL ANGEL',2,province='CARCHI',code='04',canton='ESPEJO'),
              row('EL ÁNGEL',3,province='CARCHI',code='04',canton='ESPEJO')]
        choices=manifest(rows,[decision('equivalent',[1,2],canonical_name='EL ÁNGEL')])
        report,_=plan_import(rows,decisions=choices)
        self.assertFalse(report['blocked'])
        self.assertEqual(report['would_create']['Parish'],1)
        stats=report['resolution']['counts']
        self.assertEqual(stats['exact_duplicate_rows_consolidated'],1)
        self.assertEqual(stats['equivalent_rows_consolidated'],1)
        lineage=report['resolution']['lineage']
        self.assertEqual(len(lineage),1)
        self.assertEqual({r['source_row'] for r in lineage[0]['source_rows']},{'1','2','3'})
        self.assertEqual(lineage[0]['effective']['parish'],'EL ÁNGEL')
        self.assertEqual(rows[1]['parish'],'EL ANGEL')

    def test_equivalence_cannot_cross_province_or_canton_or_choose_a_new_name(self):
        for changes in ({'canton':'OTRO'}, {'province':'OTRA'}, {}):
            with self.subTest(changes=changes):
                rows=[row('EL ÁNGEL',1),{**row('EL ANGEL',2),**changes}]
                canonical='Inventado' if not changes else 'EL ÁNGEL'
                choices=manifest(rows,[decision('equivalent',[1,2],canonical_name=canonical)])
                with self.assertRaises(ValueError):plan_import(rows,decisions=choices)

    def test_riochico_reuses_exact_bound_object_without_renaming(self):
        rows=[row('RIOCHICO (RÍO CHICO)',1)]
        choices=manifest(rows,[decision('reuse_existing',[1],target=self.target)])
        report,_=plan_import(rows,decisions=choices)
        self.assertFalse(report['blocked'])
        self.assertEqual(report['existing']['Parish'],1)
        self.assertEqual(report['would_create']['Parish'],0)
        apply_import(rows,report,decisions=choices)
        self.parish.refresh_from_db()
        self.assertEqual(self.parish.name,'RIOCHICO')
        self.assertEqual(Parish.objects.count(),2)

    def test_reuse_rejects_object_and_parent_substitution(self):
        rows=[row('RIOCHICO (RÍO CHICO)',1)]
        wrong=copy.deepcopy(self.target);wrong['parish']={'id':self.other.pk,'name':'SAN ALEJO'}
        for target, records in ((wrong,rows),(self.target,[row('RIOCHICO (RÍO CHICO)',1,canton='OTRO')]),
                                (self.target,[row('RIOCHICO (RÍO CHICO)',1,province='OTRA')])):
            with self.subTest(target=target,records=records):
                choices=manifest(records,[decision('reuse_existing',[1],target=target)])
                with self.assertRaises(ValueError):plan_import(records,decisions=choices)

    def test_pending_cases_are_quarantined_but_still_block_every_write(self):
        rows=[row('NUEVA',1),row('TIPITINI',2),row('TIPUTINI',3),row('TRUNCADA (',4),
              row('ZONA',5,province='ZONAS NO DELIMITADAS',code='90',canton='ZONA')]
        choices=manifest(rows,[decision('review',[2,3]),decision('review',[4]),decision('review',[5])])
        report,_=plan_import(rows,decisions=choices)
        self.assertTrue(report['blocked'])
        self.assertEqual(report['resolution']['counts']['excluded_source_rows'],4)
        self.assertEqual(report['resolution']['counts']['pending_cases'],3)
        self.assertEqual(report['would_create']['Parish'],1)
        with patch.object(Parish,'save',side_effect=AssertionError('write')):
            with self.assertRaises(ValueError):apply_import(rows,report,decisions=choices)
        self.assertEqual(Parish.objects.count(),2)

    def test_missing_decision_does_not_silently_clear_ambiguity(self):
        rows=[row('TIPITINI',1),row('TIPUTINI',2)]
        report,_=plan_import(rows,decisions=manifest(rows,[]))
        self.assertTrue(report['blocked'])
        self.assertTrue(report['effective_source']['possible_typographical_variants'])

    def test_forged_source_overlapping_decisions_and_unknown_rows_are_rejected(self):
        rows=[row('NUEVA',1)]
        choices=manifest(rows,[]);choices['source_rows_sha256']='wrong'
        bad=[choices,manifest(rows,[decision('review',[2])]),
             manifest(rows,[decision('review',[1]),{**decision('review',[1]),'id':'second'}])]
        for choices in bad:
            with self.subTest(choices=choices):
                with self.assertRaises(ValueError):plan_import(rows,decisions=choices)

    def test_repeat_simulation_proposes_no_new_objects_and_never_saves(self):
        rows=[row('NUEVA',1),row('TRUNCADA (',2)]
        choices=manifest(rows,[decision('review',[2])])
        with ExitStack() as stack:
            for model in (Continent,Country,Province,Canton,Parish):
                stack.enter_context(patch.object(model,'save',side_effect=AssertionError('write')))
                stack.enter_context(patch.object(model,'delete',side_effect=AssertionError('delete')))
            simulated=simulate_repeat(rows,decisions=choices)
        self.assertTrue(simulated['idempotent'])
        self.assertEqual(sum(simulated['second_would_create'].values()),0)
        self.assertTrue(simulated['second_blocked'])
        self.assertEqual(Parish.objects.count(),2)

    def test_changed_decisions_invalidate_a_previously_generated_plan(self):
        rows=[row('NUEVA',1)]
        choices=manifest(rows,[]);report,_=plan_import(rows,decisions=choices)
        changed=copy.deepcopy(choices);changed['note']='changed'
        with self.assertRaises(ValueError):apply_import(rows,report,decisions=changed)
        self.assertEqual(Parish.objects.count(),2)

    def test_command_simulation_is_dry_run_only_and_checks_original_csv_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            csv=Path(directory)/'source.csv';file=Path(directory)/'decisions.json'
            rows=[row('NUEVA',1)];write_csv(rows,csv)
            choices=manifest(rows,[]);choices['source_csv_sha256']=sha256(csv)
            file.write_text(json.dumps(choices))
            call_command('import_ecuador_geography',csv=str(csv),decisions=str(file),dry_run=True,
                         simulate_repeat=True,stdout=io.StringIO())
            self.assertEqual(Parish.objects.count(),2)
            with self.assertRaises(CommandError):call_command('import_ecuador_geography',csv=str(csv),
                decisions=str(file),apply=True,simulate_repeat=True,stdout=io.StringIO())
            choices['source_csv_sha256']='wrong';file.write_text(json.dumps(choices))
            with self.assertRaises(CommandError):call_command('import_ecuador_geography',csv=str(csv),
                decisions=str(file),dry_run=True,stdout=io.StringIO())
