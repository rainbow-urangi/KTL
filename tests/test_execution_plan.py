"""Synthetic compilation tests; no browser, model, provider or original-data writes."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from backend import execution_plan as plans
from backend.evaluators import EvaluationError


def fixture(root):
    rows = []
    for number, kind, selector in [(1, 'page_view', ''), (2, 'click', '#save'), (3, 'api_transaction', '')]:
        rows.append(dict(id=str(number), event_id='e' + str(number), session_id='session1',
            event_time=f'2026-11-09T00:00:0{number}Z', event_type='DOM_EVENT', interaction_type=kind,
            page_url='https://example.test/items', target_selector=selector, element_tag='button' if selector else '',
            input_control_type='', locators_json=json.dumps({'selector_css': selector} if selector else {}),
            target_key='css:' + selector if selector else '', input_data='', capture_run_id='test-run',
            capture_tab_id='7', capture_frame_id='0', capture_root_tab_id='7', capture_tab_path='[7]'))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    raw = stream.getvalue().encode('utf-8-sig')
    csv_sha = hashlib.sha256(raw).hexdigest()
    manifest = dict(capture_scope_version=2, active=False, run_id='test-run', target_tab_id=7,
        capture_tab_paths={'7': [7]}, csv_sha256=csv_sha, csv_byte_count=len(raw), columns=list(rows[0]),
        event_count=len(rows), event_evidence=[dict(csv_row=i, event_id=row['event_id'],
            session_id=row['session_id'], event_time=row['event_time'], tab_id=7, frame_id=0, event_sequence=i)
            for i, row in enumerate(rows, 1)])
    manifest_raw = plans.encoded(manifest)
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    (root / 'events.csv').write_bytes(raw)
    (root / 'capture.json').write_bytes(manifest_raw)
    source = dict(scenario_id='SYNTHETIC-OBSERVED', business_unit_id='SYNTHETIC', workflow_id='CAPTURE-WF-SYNTHETIC',
        status='SUCCESS', source_csv_sha256=csv_sha, source_capture_manifest_sha256=manifest_sha,
        steps=[dict(order=i, id='node' + str(i), occurrence_id='OCC-' + str(i), action=action,
                    target='observed abstract target', evidence=['e' + str(i)], source_csv_rows=[i],
                    source_session_id='session1') for i, action in enumerate(['page_entry', 'selection', 'api_confirmation'], 1)])
    plan = dict(version=1, source_scenario_sha256=plans.source_digest(source),
        observation_sources=dict(csv={'path': 'events.csv', 'sha256': csv_sha},
                                 capture_manifest={'path': 'capture.json', 'sha256': manifest_sha}),
        parameter_source='NEW_TEST_PARAMETERS', parameters={}, items=[
            dict(kind='execute', source_refs=[{'order': 1, 'event_ids': ['e1']}], action='open',
                 target={'url': rows[0]['page_url']}, expected_result='Independent definition: items screen is reached',
                 checks=[{'kind': 'url_path', 'expected': '/items'}]),
            dict(kind='execute', source_refs=[{'order': 2, 'event_ids': ['e2']}], action='click',
                 target={'by': 'css selector', 'value': '#save'}, expected_result='Independent definition: saved state is displayed',
                 checks=[{'kind': 'visible', 'target': {'by': 'css selector', 'value': '#saved-state'}}]),
            dict(kind='reference', source_refs=[{'order': 3, 'event_ids': ['e3']}], reason='Recorded API completion is an observation')])
    return source, plan


class ExecutionPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source, self.plan = fixture(self.root)
        self.observations = plans.load_observations(self.root, self.source, self.plan)

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, plan=None, source=None):
        return plans.prepare(source or self.source, plan or self.plan, observations=self.observations)

    def test_execute_reference_compilation_preserves_original_and_round_trips(self):
        original = copy.deepcopy(self.source)
        result = self.prepare()
        self.assertEqual(self.source, original)
        self.assertEqual([s['action'] for s in result['scenario']['steps']], ['open', 'click'])
        self.assertEqual(len(result['contract']['steps']), 2)
        self.assertIsNone(result['execution_plan']['source_mapping'][2]['execution_order'])
        self.assertEqual(result, self.prepare(result['execution_plan']))

    def test_api_observation_can_be_a_typed_browser_state_check_without_an_api_call(self):
        self.plan['items'][2] = dict(kind='check', source_refs=[{'order': 3, 'event_ids': ['e3']}],
            target={'by': 'css selector', 'value': '#saved-state'}, expected_result='Independent saved-state condition',
            checks=[{'kind': 'visible'}])
        result = self.prepare()
        self.assertEqual(result['scenario']['steps'][-1]['action'], 'verify')
        self.assertEqual(result['contract']['steps'][-1]['checks'][0]['kind'], 'visible')

    def test_abstract_api_confirmation_is_never_blindly_changed_to_click(self):
        self.plan['items'][2] = dict(kind='execute', source_refs=[{'order': 3, 'event_ids': ['e3']}],
            action='click', target={'by': 'css selector', 'value': '#save'}, expected_result='Invalid conversion',
            checks=[{'kind': 'visible'}])
        with self.assertRaises(EvaluationError):
            self.prepare()

    def test_page_entry_requires_real_navigation_url_instead_of_guessed_url(self):
        self.plan['items'][0]['target']['url'] = 'https://example.test/guessed'
        with self.assertRaises(EvaluationError):
            self.prepare()

    def test_execute_requires_exact_original_selector(self):
        self.plan['items'][1]['target']['value'] = '#guessed-save'
        with self.assertRaises(EvaluationError):
            self.prepare()

    def test_no_typed_check_is_not_ready(self):
        self.plan['items'][1]['checks'] = []
        with self.assertRaises(EvaluationError):
            self.prepare()

    def test_missing_duplicate_or_reordered_event_classifications_are_not_ready(self):
        variants = [self.plan['items'][:2], [self.plan['items'][0], self.plan['items'][1], self.plan['items'][1], self.plan['items'][2]],
                    [self.plan['items'][1], self.plan['items'][0], self.plan['items'][2]]]
        for items in variants:
            with self.subTest(length=len(items)):
                plan = copy.deepcopy(self.plan)
                plan['items'] = items
                with self.assertRaises(EvaluationError):
                    self.prepare(plan)

    def test_source_scenario_change_cannot_reuse_a_plan(self):
        source = copy.deepcopy(self.source)
        source['steps'][1]['action'] = 'changed'
        with self.assertRaises(EvaluationError):
            self.prepare(source=source)

    def test_saved_occurrence_mapping_cannot_be_forged(self):
        plan = self.prepare()['execution_plan']
        plan['source_mapping'][1]['source_refs'][0]['source_node_id'] = 'another-node'
        with self.assertRaises(EvaluationError):
            self.prepare(plan)

    def test_gt_and_reference_injection_is_rejected_recursively(self):
        for forbidden in [{'ground_truth': []}, {'m03_evaluation_references': {}}, {'evaluation_only': True}, {'reference': 'x'}]:
            with self.subTest(key=next(iter(forbidden))):
                plan = copy.deepcopy(self.plan)
                plan['parameters']['nested'] = forbidden
                with self.assertRaises(EvaluationError):
                    self.prepare(plan)

    def test_http_shaped_observation_dict_is_not_a_verified_bundle(self):
        with self.assertRaises(EvaluationError):
            plans.prepare(self.source, self.plan, observations=dict(self.observations))

    def test_reference_only_plan_does_not_become_an_execution_success(self):
        self.plan['items'] = [dict(kind='reference', source_refs=item['source_refs'], reason='Observation retained') for item in self.plan['items']]
        with self.assertRaises(EvaluationError):
            self.prepare()

    def test_parameters_are_not_taken_from_masked_original_data(self):
        self.plan['parameters']['new_value'] = '[MASKED]'
        with self.assertRaises(EvaluationError):
            self.prepare()

    def test_schema_refuses_malformed_observation_specs_and_path_escape(self):
        for value in [[], {'path': '../events.csv', 'sha256': self.source['source_csv_sha256']}]:
            with self.subTest(kind=type(value).__name__):
                plan = copy.deepcopy(self.plan)
                plan['observation_sources']['csv'] = value
                with self.assertRaises(EvaluationError):
                    plans.load_observations(self.root, self.source, plan)


if __name__ == '__main__':
    unittest.main()
