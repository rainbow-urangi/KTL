"""Synthetic presence-policy checks; never official collection evidence."""
import base64
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.m01 import M01CsvStore, M01ComparisonStore
from backend.m01.presence import (
    EVIDENCE_FIELDS, FORMAT, POLICY, M01PresenceStore, _actual_proof,
    _condition, _condition_proof, _edges, _maximum_pairs, _independent_maximum, verify,
)
from backend.m01.scenarios import catalog
from backend.session import RuntimeSession


PAGE = 'https://example.invalid/mypage/schedule'


def requirement(identity, *alternatives):
    return dict(id=identity, label='Synthetic required event ' + identity,
                alternatives=list(alternatives), source_step_indexes=[1], definition_basis='SYNTHETIC_TEST_ONLY')


def condition(kind='click', selector='#schedule-title', **extra):
    value = dict(event_type=kind, page_url=PAGE)
    if kind not in {'navigation', 'network'}:
        value['target_selector'] = selector
    value.update(extra)
    return value


def synthetic_catalog(requirements=None):
    requirements = requirements or [requirement('NAV', condition('navigation'))]
    value = dict(version='synthetic-presence-v1', source=dict(role='SYNTHETIC_TEST_ONLY'),
                 scenarios=[dict(scenario_id='BU' + str(index).zfill(2), scenario_name='Synthetic ' + str(index),
                                 scenario_version='synthetic-presence-v1', aliases=[], requirements=deepcopy(requirements))
                            for index in range(1, 21)])
    value['sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return value


def event(identity='synthetic-event-1', session='synthetic-session', kind='click', selector='#schedule-title', **extra):
    value = dict(event_id=identity, session_id=session, event_time='2026-11-16T00:00:00.123Z',
                 event_type='DOM_EVENT', interaction_type=kind, page_url=PAGE,
                 page_title='PRIVATE_SYNTHETIC_TITLE', target_key='css:' + selector,
                 target_selector=selector, element_tag='input', input_control_type='text',
                 input_data='PRIVATE_SYNTHETIC_VALUE', request_body='PRIVATE_SYNTHETIC_BODY')
    value.update(extra)
    return value


def graph(requirements, events):
    proof = [dict(id=item['id'], alternatives=[_condition_proof(_condition(row)) for row in item['alternatives']])
             for item in requirements]
    actual = [_actual_proof(row, index) for index, row in enumerate(events, 2)]
    return _edges(proof, actual)


class PresenceMatchingTests(unittest.TestCase):
    def test_out_of_order_events_are_present_without_claiming_order(self):
        requirements = [requirement('FIRST', condition(selector='#schedule-title')),
                        requirement('SECOND', condition(selector='#schedule-description'))]
        edges = graph(requirements, [event('b', selector='#schedule-description'), event('a')])
        self.assertEqual(_maximum_pairs(edges), {0: 1, 1: 0})
        self.assertEqual(_independent_maximum(edges), 2)

    def test_overlapping_or_conditions_use_maximum_assignment_instead_of_greedy_count(self):
        requirements = [requirement('EITHER', condition(), condition(selector='#schedule-description')),
                        requirement('TITLE', condition())]
        edges = graph(requirements, [event('a'), event('b', selector='#schedule-description')])
        self.assertEqual(_maximum_pairs(edges), {1: 0, 0: 1})
        self.assertEqual(_independent_maximum(edges), 2)
        self.assertEqual(_independent_maximum([[0], [0]]), 1)

    def test_each_alternative_requires_type_target_and_page_on_one_event(self):
        requirements = [requirement('INPUT', condition('input'))]
        rows = [event('click-only'), event('wrong-target', kind='input', selector='#unrelated-input'),
                event('wrong-page', kind='input', page_url='https://example.invalid/other')]
        self.assertEqual(_maximum_pairs(graph(requirements, rows)), {})

    def test_query_and_fragment_are_not_required_and_missing_id_never_matches(self):
        requirements = [requirement('NAV', condition('navigation'))]
        rows = [event('', kind='page_view', page_url=PAGE + '?token=PRIVATE_QUERY#fragment')]
        self.assertEqual(_maximum_pairs(graph(requirements, rows)), {})
        rows[0]['event_id'] = 'valid-synthetic-event'
        self.assertEqual(len(_maximum_pairs(graph(requirements, rows))), 1)

    def test_stable_css_components_keep_boundaries_and_explicit_field_positions(self):
        selector = '.profile-editor > label:nth-of-type(2) > input'
        requirements = [requirement('FIELD', condition(selector=selector, selector_match='contains'))]
        accepted = event(selector='main > .profile-editor:nth-of-type(1) > label:nth-of-type(2) > input:nth-of-type(1)')
        wrong_field = event(selector='.profile-editor > label:nth-of-type(3) > input')
        wrong_component = event(selector='.profile-editor-copy > label:nth-of-type(2) > input')
        self.assertEqual(len(_maximum_pairs(graph(requirements, [accepted]))), 1)
        self.assertEqual(_maximum_pairs(graph(requirements, [wrong_field, wrong_component])), {})

    def test_api_prefix_is_explicit_and_segment_bounded(self):
        requirements = [requirement('API', condition('network', api_path='/api/cards', api_method='GET', api_match='prefix'))]
        valid = event('a', kind='fetch_request', api_path='/api/cards/123?private=ignored', api_method='GET')
        invalid = event('b', kind='fetch_request', api_path='/api/cards-copy/123', api_method='GET')
        self.assertEqual(len(_maximum_pairs(graph(requirements, [valid]))), 1)
        self.assertEqual(_maximum_pairs(graph(requirements, [invalid])), {})
        with self.assertRaises(EvaluationError):
            _condition(condition('network', api_path='/', api_method='GET', api_match='prefix'))

    def test_popup_lifecycle_event_type_is_normalized_without_accepting_close(self):
        requirements = [requirement('OPEN', condition('popup', selector='.schedule-modal', interaction_type='popup_open', selector_match='contains'))]
        opened = event(event_type='popup_open', interaction_type='', selector='.schedule-modal')
        closed = event(event_type='popup_close', interaction_type='', selector='.schedule-modal')
        self.assertEqual(len(_maximum_pairs(graph(requirements, [opened]))), 1)
        self.assertEqual(_maximum_pairs(graph(requirements, [closed])), {})

    def test_unsafe_or_broad_selectors_and_unknown_predicates_are_rejected(self):
        for selector in ('button', '.btn', '.button', 'input[value="PRIVATE"]', '.specific *'):
            with self.subTest(selector=selector), self.assertRaises(EvaluationError):
                _condition(condition(selector=selector))
        with self.assertRaises(EvaluationError):
            _condition(condition(target_text='PRIVATE'))


class PresencePersistenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-synthetic-m01-presence-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = dict(targets={'M01': 65}, integration_datasets={})
        self.session = RuntimeSession()
        self.store = M01PresenceStore(self.root, session=self.session)

    def upload(self, rows):
        fields = list(dict.fromkeys(key for row in rows for key in row))
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        raw = output.getvalue().encode('utf-8-sig')
        report = M01CsvStore(self.root, session=self.session).upload(
            dict(filename='synthetic-presence.csv', csv_base64=base64.b64encode(raw).decode()), self.config)
        return report['dataset']['dataset_id'], raw

    def compare(self, dataset, fixed=None, **extra):
        fixed = fixed or synthetic_catalog()
        payload = dict(dataset_id=dataset, catalog_version=fixed['version'], catalog_sha256=fixed['sha256'], **extra)
        with patch('backend.m01.presence._catalog', return_value=fixed):
            return self.store.compare_all(payload, self.config)

    def test_all_twenty_results_verify_and_keep_existing_storage_consumers(self):
        dataset, raw = self.upload([event(kind='page_view')])
        result = self.compare(dataset)
        self.assertEqual((result['scenario_count'], result['completed_count'], result['candidate_count']), (20, 20, 20))
        self.assertEqual(result['representative']['scenario_id'], 'BU01')
        self.assertEqual(result['result']['matching_policy'], POLICY)
        original = self.root / 'data/development/m01_uploads' / dataset / 'source.csv'
        self.assertEqual(original.read_bytes(), raw)
        saved = M01ComparisonStore(self.root, session=self.session)
        for candidate in result['candidates']:
            current = candidate['result']
            folder = self.store.directory / current['comparison_id']
            self.assertEqual(saved.read(current['comparison_id']), current)
            self.assertEqual(candidate['truth'], current['presence_truth'])
            self.assertTrue(verify((folder / 'evidence.csv').read_bytes(), current)['verified'])
            self.assertTrue(verify((folder / 'evidence.csv').read_bytes())['verified'])
            self.assertEqual(set(path.name for path in folder.iterdir()), {'result.json', 'truth.csv', 'truth_snapshot.json', 'evidence.csv', 'verification.json', 'manifest.json'})
            self.assertIsNone(current['official_pass'])
        # The legacy event-results endpoint dispatches the new verifier through score.py.
        exported = saved.event_results(result['result']['comparison_id'])
        self.assertIn(b'expected_event_id,matched_event_id,collected,missing_fields,event_type', exported)

    def test_sessions_are_never_combined_and_best_session_is_stored_explicitly(self):
        required = [requirement('TITLE', condition()), requirement('BODY', condition(selector='#schedule-description'))]
        dataset, _ = self.upload([event('a', session='first'), event('b', session='second', selector='#schedule-description')])
        result = self.compare(dataset, synthetic_catalog(required))
        self.assertEqual(result['candidate_count'], 40)
        self.assertEqual(result['session_id'], 'first')
        self.assertTrue(all(candidate['result']['measurement']['c1'] == 50 for candidate in result['candidates']))
        selected = self.compare(dataset, synthetic_catalog(required), session_id='second')
        self.assertEqual(selected['candidate_count'], 20)
        self.assertEqual(selected['result']['session_id'], 'second')

    def test_duplicate_event_ids_count_once_but_raw_rows_remain_in_c2_c3(self):
        required = [requirement('ONE', condition()), requirement('TWO', condition())]
        original = event(page_title='')
        dataset, _ = self.upload([original, deepcopy(original)])
        result = self.compare(dataset, synthetic_catalog(required))['result']
        self.assertEqual(result['summary']['matched_count'], 1)
        self.assertEqual(result['summary']['duplicate_event_rows'], 1)
        counts = result['measurement']['counts']
        self.assertEqual((counts['total_collected_events'], counts['missing_required_field_count']), (2, 2))
        self.assertAlmostEqual(result['measurement']['c2'], 100 / 6)

    def test_conflicting_ids_and_invalid_sessions_fail_before_any_comparison_is_written(self):
        for rows in ([event('same'), event('same', selector='#schedule-description')], [event(session='')]):
            with self.subTest(kind='conflict' if len(rows) == 2 else 'missing-session'):
                dataset, _ = self.upload(rows)
                before = sorted(self.store.directory.glob('*'))
                with self.assertRaises(EvaluationError):
                    self.compare(dataset)
                self.assertEqual(sorted(self.store.directory.glob('*')), before)

    def test_private_source_values_and_observed_selectors_never_enter_evidence(self):
        raw_selector = '.PRIVATE_SYNTHETIC_SELECTOR > input#schedule-title'
        dataset, _ = self.upload([event(selector=raw_selector, kind='change')])
        fixed = synthetic_catalog([requirement('INPUT', condition('input', selector_match='contains'))])
        current = self.compare(dataset, fixed)['result']
        evidence = (self.store.directory / current['comparison_id'] / 'evidence.csv').read_bytes()
        self.assertEqual(current['summary']['matched_count'], 1)
        serialized = json.dumps(current).encode()
        for private in (b'PRIVATE_SYNTHETIC_TITLE', b'PRIVATE_SYNTHETIC_VALUE', b'PRIVATE_SYNTHETIC_BODY', b'PRIVATE_SYNTHETIC_SELECTOR'):
            self.assertNotIn(private, evidence)
            self.assertNotIn(private, serialized)
        self.assertNotIn(b'synthetic-session', evidence)

    def test_catalog_snapshot_size_and_session_limits_fail_before_partial_results(self):
        dataset, _ = self.upload([event(str(index), session='session-' + str(index)) for index in range(11)])
        with self.assertRaises(EvaluationError):
            self.compare(dataset)
        self.assertFalse(self.store.directory.exists())
        fixed = synthetic_catalog()
        with patch('backend.m01.presence._catalog', return_value=fixed), self.assertRaises(EvaluationError):
            self.store.compare_all(dict(dataset_id=dataset, catalog_version=fixed['version'], catalog_sha256='0' * 64), self.config)
        with patch('backend.m01.presence.MAX_EVIDENCE_ROWS', 1), self.assertRaises(EvaluationError):
            self.compare(dataset, session_id='session-0')

    def test_evidence_rejects_event_reuse_score_tampering_and_policy_tampering(self):
        required = [requirement('ONE', condition()), requirement('TWO', condition())]
        dataset, _ = self.upload([event()])
        result = self.compare(dataset, synthetic_catalog(required))['result']
        raw = (self.store.directory / result['comparison_id'] / 'evidence.csv').read_bytes()
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        expected = [row for row in rows if row['row_kind'] == 'EXPECTED']
        matched = next(row for row in expected if row['status'] == 'MATCHED')
        missing = next(row for row in expected if row['status'] == 'MISSING')
        for name in ('matched_event_id', 'matched_csv_row', 'matched_alternative', 'status'):
            missing[name] = matched[name]
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=EVIDENCE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        with self.assertRaises(EvaluationError):
            verify(output.getvalue().encode('utf-8-sig'))
        changed = deepcopy(result)
        changed['measurement']['c1'] = 100
        with self.assertRaises(EvaluationError):
            verify(raw, changed)
        changed = deepcopy(result)
        changed['matching_policy'] = 'UNVERIFIED_OTHER_POLICY'
        with self.assertRaises(EvaluationError):
            verify(raw, changed)

    def test_actual_fixed_catalog_is_accepted_without_runtime_or_provider_calls(self):
        dataset, _ = self.upload([event(kind='page_view', page_url='https://rainbowlab.ai.kr/mypage/personal-info')])
        fixed = catalog()
        with patch('subprocess.Popen', side_effect=AssertionError('No browser or provider allowed')):
            result = self.store.compare_all(dict(dataset_id=dataset, catalog_version=fixed['version'], catalog_sha256=fixed['sha256']), self.config)
        self.assertEqual(len(result['candidates']), 20)
        self.assertEqual(result['candidates'][0]['result']['summary']['matched_count'], 1)


if __name__ == '__main__':
    unittest.main()
