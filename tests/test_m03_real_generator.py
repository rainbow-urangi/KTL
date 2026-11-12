import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backend.evaluators import EvaluationError
from backend.m03_integration import generate, evaluate_scenarios, validate_scenario_result


class RealGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = dict(processes=[dict(canonical_instance_id='WF-test', source_process_id='PM-test',
            business_steps=[dict(action_type='INPUT', target='Example field', step_order=1,
                resolution_status='RESOLVED', source_event_ids=['event-test'], source_node_ids=['node-test'],
                generated_step_id='step-test', fields=[dict(label='Example field')])])])
        self.request = dict(business_unit_id='DEV-test', workflow_id='WF-test', generator_mode='REAL')
        self.bind()

    def bind(self):
        path = self.root / 'observed.json'
        path.write_text(json.dumps(self.snapshot))
        self.config = dict(m03_real_generator=dict(snapshot_path='observed.json',
            snapshot_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

    def test_real_schema_provenance_and_determinism(self):
        result = generate(self.root, self.config, self.request)
        self.assertTrue(validate_scenario_result(result)['success'])
        self.assertEqual(result, generate(self.root, self.config, self.request))
        self.assertEqual(result['steps'][0]['source_event_ids'], ['event-test'])
        self.assertFalse(result['synthetic'])
        self.assertIsNone(result['official_pass'])

    def test_official_and_tampered_and_unknown_workflow_rejected(self):
        for changes in (dict(run_mode='OFFICIAL'), dict(workflow_id='unknown')):
            with self.assertRaises(EvaluationError):
                generate(self.root, self.config, dict(self.request, **changes))
        (self.root / 'observed.json').write_text('{}')
        with self.assertRaises(EvaluationError):
            generate(self.root, self.config, self.request)

    def test_missing_evidence_unknown_action_and_order_fail(self):
        for changes in (dict(source_event_ids=[]), dict(action_type='UNRESOLVED'),
                        dict(target=''), dict(step_order=2)):
            snapshot = copy.deepcopy(self.snapshot)
            self.snapshot['processes'][0]['business_steps'][0].update(changes)
            self.bind()
            result = generate(self.root, self.config, self.request)
            self.assertEqual(result['status'], 'FAILED')
            self.assertFalse(validate_scenario_result(result)['success'])
            self.snapshot = snapshot

    def test_development_eight_of_ten_retains_failures(self):
        rows = []
        for i in range(10):
            self.snapshot['processes'][0]['business_steps'][0]['action_type'] = 'INPUT' if i < 8 else 'UNRESOLVED'
            self.bind()
            rows.append(generate(self.root, self.config, dict(self.request, business_unit_id='DEV-'+str(i))))
        score, count, details, evidence = evaluate_scenarios(dict(run_mode='DEVELOPMENT', scenarios=rows))
        self.assertEqual((score, count), (80, 10))
        self.assertEqual(details['raw_counts']['failed_scenario_count'], 2)
        self.assertEqual(len(evidence), 10)

    def test_provenance_requires_nonempty_array_of_nonblank_strings(self):
        invalid = (None, '', 'event-test', 1, True, {}, {'id': 'event-test'},
                   [], [''], ['   '], [None], [1], [True], ['valid', ''], ['valid', 2])
        for field in ('source_event_ids', 'source_node_ids'):
            for value in invalid:
                with self.subTest(field=field, value=value):
                    snapshot = copy.deepcopy(self.snapshot)
                    self.snapshot['processes'][0]['business_steps'][0][field] = value
                    self.bind()
                    result = generate(self.root, self.config, self.request)
                    self.assertEqual(result['status'], 'FAILED')
                    self.assertEqual(result['steps'], [])
                    self.assertFalse(validate_scenario_result(result)['success'])
                    self.snapshot = snapshot

    def test_step_order_requires_exact_integer(self):
        for value in (True, False, 1.0, '1', None):
            with self.subTest(value=value):
                self.snapshot['processes'][0]['business_steps'][0]['step_order'] = value
                self.bind()
                result = generate(self.root, self.config, self.request)
                self.assertEqual(result['status'], 'FAILED')
                self.assertEqual(result['steps'], [])
                self.assertFalse(validate_scenario_result(result)['success'])

    def test_menu_enter_normalizes_to_navigation_with_source_evidence(self):
        source = self.snapshot['processes'][0]['business_steps'][0]
        source.update(action_type='MENU_ENTER', target='Unseen synthetic menu')
        self.bind()
        result = generate(self.root, self.config, self.request)
        self.assertTrue(validate_scenario_result(result)['success'])
        step = result['steps'][0]
        self.assertEqual(step['action'], 'NAVIGATE')
        self.assertEqual(step['target'], source['target'])
        for key in ('source_event_ids', 'source_node_ids'):
            self.assertEqual(step[key], source[key])
        self.assertEqual(step['source_step_id'], source['generated_step_id'])
        self.assertEqual(result, generate(self.root, self.config, self.request))

    def test_menu_enter_never_fabricates_target_or_resolution_or_order(self):
        original = copy.deepcopy(self.snapshot)
        for changes in (dict(target=None), dict(target=''), dict(target='   '),
                        dict(target='x'*257), dict(resolution_status='UNRESOLVED'),
                        dict(source_event_ids=[]), dict(source_node_ids=[]), dict(step_order=2)):
            with self.subTest(changes=changes):
                self.snapshot = copy.deepcopy(original)
                source = self.snapshot['processes'][0]['business_steps'][0]
                source.update(action_type='MENU_ENTER', menu_page='Not a fallback target')
                source.update(changes)
                self.bind()
                result = generate(self.root, self.config, self.request)
                self.assertEqual(result['steps'], [])
                self.assertEqual(result['status'], 'FAILED')

    def test_menu_enter_preserves_order_gaps_and_unsupported_steps(self):
        source = self.snapshot['processes'][0]['business_steps'][0]
        source.update(action_type='MENU_ENTER')
        unsupported = dict(source, action_type='SELECT', step_order=2)
        final = dict(source, action_type='SAVE', step_order=3)
        self.snapshot['processes'][0]['business_steps'] = [source, unsupported, final]
        self.bind()
        result = generate(self.root, self.config, self.request)
        self.assertEqual([s['order'] for s in result['steps']], [1, 3])
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(validate_scenario_result(result)['step_order_valid'])
