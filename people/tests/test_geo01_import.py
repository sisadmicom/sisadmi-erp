"""GEO-01 contracts on isolated PostgreSQL test data."""
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, SimpleTestCase

from people.models.geography import Continent, Country, Province, Canton, Parish
from people.services.geography_catalog_parser import analyze, parse_bbox, read_csv, write_csv
from people.services.geography_catalog_import import plan_import, apply_import


def row(province='MANABÍ', canton='PORTOVIEJO', parish='RÍO CHICO', code='13'):
    return dict(province_code=code, province=province, canton=canton, parish=parish,
                source_page='1', source_row='1')


class Geo01ParserTests(SimpleTestCase):
    def test_geometry_preserves_accents_and_handles_shifted_or_merged_text(self):
        words = [('13', 79, 87, 85), ('MANABÍ', 145, 180, 85),
                 ('PORTOVIEJO', 248, 300, 85), ('ATOCHA', 404, 433, 83.7),
                 ('–', 435, 439, 83.7), ('FICOA', 441, 462, 83.7)]
        xml = '<html xmlns="http://www.w3.org/1999/xhtml"><page>' + ''.join(
            f'<line xMin="{group[0][1]}" yMin="{group[0][3]}">' + ''.join(
            f'<word xMin="{a}" xMax="{b}" yMin="{y}">{t}</word>' for t,a,b,y in group) + '</line>'
            for group in ([words[0]], [words[1]], [words[2]], words[3:])) + '</page></html>'
        result = parse_bbox(xml)
        self.assertEqual(result[0]['province'], 'MANABÍ')
        self.assertEqual(result[0]['parish'], 'ATOCHA – FICOA')
        self.assertEqual(result[0]['source_page'], '1')

    def test_long_parish_crossing_cell_border_is_not_moved_into_canton(self):
        groups = [[('20',79,87)], [('GALAPAGOS',140,180)], [('SAN CRISTÓBAL',250,310)],
                  [('ISLA',321,338), ('SANTA MARÍA',340,390)]]
        xml = '<html xmlns="http://www.w3.org/1999/xhtml"><page>' + ''.join(
            f'<line xMin="{g[0][1]}" yMin="85">' + ''.join(
            f'<word xMin="{a}" xMax="{b}" yMin="85">{t}</word>' for t,a,b in g) + '</line>'
            for g in groups) + '</page></html>'
        result=parse_bbox(xml)[0]
        self.assertEqual(result['canton'],'SAN CRISTÓBAL')
        self.assertEqual(result['parish'],'ISLA SANTA MARÍA')

    def test_merged_canton_parish_uses_separated_gap_and_rejects_uncertain_cells(self):
        groups = [[('09',79,87)], [('GUAYAS',155,184)],
                  [('CORONEL',217,251), ('MARCELINO',253,294), ('MARIDUEÑA',296,338),
                   ('CORONEL',347,381), ('MARCELINO',383,424), ('MARIDUEÑA',426,468)]]
        xml = '<html xmlns="http://www.w3.org/1999/xhtml"><page>' + ''.join(
            f'<line xMin="{g[0][1]}" yMin="85">' + ''.join(
            f'<word xMin="{a}" xMax="{b}" yMin="85">{t}</word>' for t,a,b in g) + '</line>'
            for g in groups) + '</page></html>'
        result=parse_bbox(xml)[0]
        self.assertEqual(result['canton'],'CORONEL MARCELINO MARIDUEÑA')
        self.assertEqual(result['parish'],'CORONEL MARCELINO MARIDUEÑA')
        with self.assertRaises(ValueError): parse_bbox(xml.replace('xMin="347"','xMin="340"'))

    def test_utf8_csv_roundtrip_keeps_leading_zero_and_original_spelling(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.csv'
            values = [row('CAÑAR', 'CAÑAR', 'EL ÁNGEL', '03')]
            write_csv(values, path)
            self.assertEqual(read_csv(path), values)
            path.write_text('province_code,province\n03,CAÑAR\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                read_csv(path)
            path.write_text('province_code,province,canton,parish,source_page,source_row\n03,"CAÑAR', encoding='utf-8')
            with self.assertRaises(ValueError):
                read_csv(path)

    def test_duplicates_are_parent_scoped_and_equivalences_are_reported(self):
        values = [row(parish='EL ÁNGEL'), row(parish='EL ÁNGEL'), row(parish='EL ANGEL'),
                  row(canton='OTRO CANTÓN', parish='EL ÁNGEL')]
        result = analyze(values)
        self.assertEqual(result['duplicate_extra_rows'], 1)
        self.assertEqual(result['distinct_cantons'], 2)
        self.assertEqual(len(result['equivalent_names']), 1)
        near = analyze([row(parish='TIPITINI'), row(parish='TIPUTINI')])
        self.assertEqual(near['possible_typographical_variants'][0]['names'], ['TIPITINI', 'TIPUTINI'])

    def test_incomplete_names_non_provinces_and_truncation_are_not_silently_fixed(self):
        result = analyze([row(parish=''), row(parish='LA UNIÓN ('), row(code='90')])
        self.assertEqual({v['kind'] for v in result['ambiguities']},
                         {'incomplete_or_invalid_name', 'unbalanced_parentheses',
                          'non_province_code', 'province_name_has_multiple_codes'})


class Geo01ImportTests(TestCase):
    def test_dry_run_does_not_write_and_predicts_complete_chain(self):
        report, _ = plan_import([row()], country_code='593')
        self.assertFalse(report['conflicts'])
        self.assertEqual(report['would_create'], {m.__name__: 1 for m in (Continent,Country,Province,Canton,Parish)})
        self.assertFalse(Continent.objects.exists())

    def test_atomic_import_and_second_execution_are_idempotent(self):
        values = [row(), row()]
        report, _ = plan_import(values, country_code='593')
        apply_import(values, report, country_code='593')
        parish = Parish.objects.get()
        self.assertEqual(parish.canton.province.country.continent.name, 'América')
        self.assertEqual(parish.canton.province.country.name, 'Ecuador')
        second, _ = plan_import(values, country_code='593')
        self.assertEqual(sum(second['would_create'].values()), 0)
        apply_import(values, second, country_code='593')
        self.assertEqual(Parish.objects.count(), 1)

    def test_existing_equivalent_names_and_country_code_are_preserved(self):
        continent=Continent.objects.create(name='America')
        country=Country.objects.create(name='ECUADOR', code='593', continent=continent)
        Province.objects.create(name='MANABI', country=country)
        values=[row()]
        report,_=plan_import(values)
        self.assertFalse(report['conflicts'])
        apply_import(values,report)
        continent.refresh_from_db();country.refresh_from_db()
        self.assertEqual((continent.name,country.name,country.code),('America','ECUADOR','593'))
        self.assertEqual(Province.objects.get().name,'MANABI')

    def test_ambiguous_existing_names_and_possible_alias_block_all_writes(self):
        continent=Continent.objects.create(name='América')
        country=Country.objects.create(name='Ecuador',code='593',continent=continent)
        province=Province.objects.create(name='MANABÍ',country=country)
        canton=Canton.objects.create(name='PORTOVIEJO',province=province)
        Parish.objects.create(name='RIOCHICO',canton=canton)
        values=[row(parish='RIOCHICO (RÍO CHICO)')]
        report,_=plan_import(values)
        self.assertIn('possible_existing_alias',{c['kind'] for c in report['conflicts']})
        with self.assertRaises(ValueError): apply_import(values,report)
        self.assertEqual(Parish.objects.count(),1)
        Continent.objects.create(name='America')
        report,_=plan_import(values)
        self.assertIn('ambiguous_existing_name',{c['kind'] for c in report['conflicts']})

    def test_source_equivalences_and_model_lengths_block_import(self):
        values=[row(parish='EL ÁNGEL'),row(parish='EL ANGEL'),row(canton='X'*101)]
        report,_=plan_import(values,country_code='593')
        self.assertIn('model_max_length',{c['kind'] for c in report['conflicts']})
        with self.assertRaises(ValueError): apply_import(values,report,country_code='593')
        self.assertFalse(Country.objects.exists())

    def test_wrong_country_parent_and_country_code_collision_are_conflicts(self):
        continent=Continent.objects.create(name='Otro continente')
        Country.objects.create(name='Ecuador',code='593',continent=continent)
        report,_=plan_import([row()],country_code='593')
        self.assertIn('country_parent_conflict',{c['kind'] for c in report['conflicts']})
        Country.objects.all().delete()
        Country.objects.create(name='Otro país',code='593',continent=continent)
        report,_=plan_import([row()],country_code='593')
        self.assertIn('country_code_collision',{c['kind'] for c in report['conflicts']})

    def test_failure_rolls_back_whole_geographic_operation(self):
        values=[row()]; report,_=plan_import(values,country_code='593')
        with patch.object(Parish,'save',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError): apply_import(values,report,country_code='593')
        for model in (Continent,Country,Province,Canton,Parish): self.assertFalse(model.objects.exists())

    def test_stale_approval_is_rejected_without_creating_children(self):
        values=[row()]; report,_=plan_import(values,country_code='593')
        Continent.objects.create(name='América')
        with self.assertRaises(ValueError): apply_import(values,report,country_code='593')
        self.assertFalse(Country.objects.exists())

    def test_command_requires_dry_run_and_binds_apply_to_approved_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'catalog.csv'; report_path=Path(directory)/'report.json'
            write_csv([row()],path)
            with self.assertRaises(CommandError): call_command('import_ecuador_geography',csv=str(path),stdout=io.StringIO())
            call_command('import_ecuador_geography',csv=str(path),dry_run=True,country_code='593',report=str(report_path),stdout=io.StringIO())
            self.assertFalse(Country.objects.exists())
            self.assertTrue(json.loads(report_path.read_text())['dry_run'])
            with self.assertRaises(CommandError): call_command('import_ecuador_geography',csv=str(path),apply=True,stdout=io.StringIO())
