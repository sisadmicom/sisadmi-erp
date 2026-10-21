"""Plan comparison contracts without connections or writes to PostgreSQL."""
import copy
import json
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from people.services import geography_catalog_import as importer
from people.services.geography_catalog_parser import read_csv


class Geo01PlanComparisonTests(SimpleTestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / 'data/geo01/phase2'
        self.audit = json.loads((root/'verification.json').read_text())
        self.rows = read_csv(root/'ecuador_2016_partial.csv')
        self.approved = json.loads((root/'dry_run.json').read_text())
        # Freeze only the importer's report context, never Django's real DB
        # settings: these artifact-based tests run identically inside TEST.
        self.enterContext(patch.object(importer, 'connection', SimpleNamespace(
            settings_dict={'NAME': self.approved['database_name']},
            vendor=self.approved['database_vendor'])))
        self.current, self.nodes = importer.plan_import(
            self.rows, _snapshot=self.audit['database_before'])

    def apply_without_database(self, approved):
        # The atomic wrapper is intentionally not entered: SimpleTestCase also
        # prohibits database access. ORM writes are intercepted, never executed.
        with ExitStack() as stack:
            stack.enter_context(patch.object(importer, 'snapshots', return_value=self.audit['database_before']))
            saves = []
            for model in importer.MODELS:
                stack.enter_context(patch.object(model.objects, 'get', return_value=model()))
                stack.enter_context(patch.object(model, 'full_clean'))
                saves.append(stack.enter_context(patch.object(model, 'save')))
            try:
                result = importer.apply_import.__wrapped__(self.rows, approved)
            except ValueError:
                for save in saves:
                    save.assert_not_called()
                raise
            return result, sum(save.call_count for save in saves)

    def test_json_roundtrip_accepts_tuple_list_parent_paths(self):
        self.assertIsInstance(self.current['matches'][1]['parent'], tuple)
        self.assertIsInstance(self.approved['matches'][1]['parent'], list)
        result, saves = self.apply_without_database(self.approved)
        self.assertEqual(result['created'], self.approved['would_create'])
        self.assertEqual(saves, 1596)

    def test_changed_parish_is_rejected_before_any_save(self):
        altered = copy.deepcopy(self.approved)
        self.assertEqual(altered['matches'][-1]['entity'], 'Parish')
        altered['matches'][-1]['source_name'] = 'MODIFICADA'
        with self.assertRaises(ValueError):
            self.apply_without_database(altered)

    def test_changed_parent_path_is_rejected_before_any_save(self):
        altered = copy.deepcopy(self.approved)
        altered['matches'][-1]['parent'][-1] = 'otro canton'
        with self.assertRaises(ValueError):
            self.apply_without_database(altered)

    def test_changed_counts_are_rejected_before_any_save(self):
        altered = copy.deepcopy(self.approved)
        altered['would_create']['Parish'] += 1
        with self.assertRaises(ValueError):
            self.apply_without_database(altered)

    def test_invalid_hash_is_rejected_before_any_save(self):
        for field in ('source_rows_sha256', 'database_snapshot_sha256'):
            with self.subTest(field=field):
                altered = copy.deepcopy(self.approved)
                altered[field] = '0'*64
                with self.assertRaises(ValueError):
                    self.apply_without_database(altered)

    def test_additional_operation_is_rejected_before_any_save(self):
        altered = copy.deepcopy(self.approved)
        altered['operations'] = [{'operation':'CREATE','entity':'Parish','name':'ADICIONAL'}]
        with self.assertRaises(ValueError):
            self.apply_without_database(altered)

    def test_full_canonical_hash_is_checked_even_if_structural_equality_accepts_types(self):
        # Python equates False and 0; their JSON content/hash must remain distinct.
        altered = copy.deepcopy(self.approved)
        altered['blocked'] = 0
        self.assertEqual(importer.canonical_plan(self.current), altered)
        with self.assertRaises(ValueError):
            self.apply_without_database(altered)

    def test_full_structure_is_checked_even_if_hashes_match(self):
        altered = copy.deepcopy(self.approved)
        altered['would_create']['Parish'] += 1
        with patch.object(importer, 'digest', return_value='same-hash'):
            with self.assertRaises(ValueError):
                self.apply_without_database(altered)

    def test_repeat_simulation_still_proposes_zero_additions_without_saving(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(importer, 'snapshots', return_value=self.audit['database_before']))
            for model in importer.MODELS:
                stack.enter_context(patch.object(model, 'save', side_effect=AssertionError('write')))
                stack.enter_context(patch.object(model, 'delete', side_effect=AssertionError('delete')))
            repeat = importer.simulate_repeat(self.rows)
        self.assertTrue(repeat['idempotent'])
        self.assertEqual(sum(repeat['second_would_create'].values()), 0)
        self.assertEqual(repeat['actual_writes'], 0)
