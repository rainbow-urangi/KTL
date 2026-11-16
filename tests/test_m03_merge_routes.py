"""Synthetic merge-route contracts only; no real inputs, network, model or browser."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.m03_integration import development_context, generate, uses_observed_generator
from backend.m03_provenance import encoded, generate_recorded


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class M03MergeRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-m03-merge-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for target in ('urllib.request.urlopen', 'socket.create_connection', 'subprocess.Popen'):
            self.enterContext(patch(target, side_effect=AssertionError('No network/model/browser in merge test')))
        self.path = self.root / 'synthetic-observed.json'
        self.snapshot = dict(processes=[dict(canonical_instance_id='WF-OBSERVED', source_process_id='PM-SYNTHETIC',
            business_steps=[dict(action_type='INPUT', target='Synthetic business field', step_order=1,
                resolution_status='RESOLVED', source_event_ids=['SYNTHETIC-E1'], source_node_ids=['SYNTHETIC-N1'],
                generated_step_id='SYNTHETIC-STEP1', fields=[])])])
        self.path.write_bytes(encoded(self.snapshot))
        self.config = dict(m03_real_generator=dict(snapshot_path=self.path.name,
                           snapshot_sha256=sha(self.path.read_bytes())))
        self.request = dict(business_unit_id='BU-OBSERVED', workflow_id='WF-OBSERVED',
                            generator_mode='REAL', run_mode='DEVELOPMENT')

    def response(self, request=None):
        request = request or self.request
        return dict(business_unit_id=request['business_unit_id'], workflow_id=request['workflow_id'],
                    scenario_id='SYNTHETIC-SCN', status='SUCCESS',
                    steps=[dict(order=1, action='click', target='Synthetic business control')])

    def add_feature(self):
        folder = self.root / 'data/analysis'
        folder.mkdir(parents=True)
        source = folder / 'feature.json'
        source.write_bytes(encoded(dict(observed_events=['SYNTHETIC-FEATURE-E1'])))
        manifest = folder / 'manifest.json'
        manifest.write_bytes(encoded(dict(dataset_id='synthetic-feature-analysis',
            workflow_ids=['WF-FEATURE'], files=[dict(path=source.name, sha256=sha(source.read_bytes()))])))
        definition = dict(business_unit_id='BU-FEATURE', workflow_id='WF-FEATURE', business_name='Synthetic feature',
                          start_screen='/synthetic', required_procedures=['Synthetic observed procedure'],
                          end_condition='Synthetic procedure transferred')
        self.config.update(adapters=dict(scenario_generation=['SYNTHETIC-NEVER-SPAWN']),
            m03=dict(generator_mode='REAL', transport='SUBPROCESS', source_module='synthetic-adapter',
                     source_version='synthetic-v1', business_units=[definition],
                     input_manifest=manifest.relative_to(self.root).as_posix()))
        return dict(self.request, business_unit_id='BU-FEATURE', workflow_id='WF-FEATURE')

    def stored(self, identity):
        folder = self.root / 'results/m03_generations' / identity
        return folder, json.loads((folder / 'receipt.json').read_bytes())

    def test_selector_keeps_explicit_feature_units_and_dataset_scopes(self):
        feature = self.add_feature()
        self.assertTrue(uses_observed_generator(self.config, self.request))
        self.assertFalse(uses_observed_generator(self.config, feature))
        for change in (dict(dataset_id='EXPLICIT'), dict(dataset_id=None), dict(run_mode='OFFICIAL'),
                       dict(run_mode='REFERENCE'), dict(generator_mode='MOCK')):
            with self.subTest(change=change):
                self.assertFalse(uses_observed_generator(self.config, dict(self.request, **change)))
        self.assertFalse(uses_observed_generator(self.config, None))
        self.assertFalse(uses_observed_generator({}, self.request))

    def test_observed_generation_preserves_snapshot_bound_start_response_and_receipt(self):
        before = self.path.read_bytes()
        with patch('backend.m03_integration._real_input', side_effect=AssertionError('No fabricated canonical manifest')):
            result = generate_recorded(self.root, self.config, self.request)
        folder, receipt = self.stored(result['origin_generation_id'])
        started = json.loads((folder / 'started.json').read_bytes())
        self.assertEqual(receipt['status'], 'COMPLETED')
        self.assertEqual(started['analysis_input'], receipt['analysis_input'])
        self.assertEqual(receipt['analysis_input'], dict(kind='OBSERVED_PROCESS_SNAPSHOT',
            snapshot_path=self.path.name, snapshot_sha256=sha(before),
            files=[dict(path=self.path.name, sha256=sha(before))]))
        self.assertIsNone(receipt['dataset'])
        self.assertIsNone(receipt['reference_at_generation'])
        self.assertNotIn('manifest_path', receipt['analysis_input'])
        self.assertEqual(sha((folder / 'response.json').read_bytes()), receipt['response_sha256'])
        self.assertEqual(json.loads((folder / 'response.json').read_bytes()), result)
        self.assertEqual(result['source_snapshot_sha256'], sha(before))
        self.assertFalse(result['official'])
        self.assertEqual(result['data_class'], 'DEVELOPMENT')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / 'data/evaluation').exists())

    def test_coexisting_feature_path_retains_verified_input_and_never_calls_observed(self):
        request = self.add_feature()
        with patch('backend.m03_real_generator.generate_observed', side_effect=AssertionError('Feature priority lost')), \
             patch('backend.m03_integration.call_adapter', return_value=self.response(request)) as adapter:
            result = generate_recorded(self.root, self.config, request)
        adapter.assert_called_once()
        _, name, sent, _ = adapter.call_args.args
        self.assertEqual(name, 'scenario_generation')
        self.assertEqual(set(sent), {'business_unit_id', 'workflow_id', 'business_definition', 'analysis_input'})
        self.assertEqual(sent['business_definition']['business_unit_id'], 'BU-FEATURE')
        _, receipt = self.stored(result['origin_generation_id'])
        self.assertEqual(receipt['analysis_input'], sent['analysis_input'])
        self.assertEqual(receipt['analysis_input']['manifest_path'], 'data/analysis/manifest.json')
        self.assertNotIn('m03_evaluation_references', sent)

    def test_wrong_unit_with_an_explicit_registered_dataset_cannot_fall_back_to_observed(self):
        self.add_feature()
        context = development_context(self.root, self.config)
        with patch('backend.m03_real_generator.generate_observed', side_effect=AssertionError('Scoped fallback forbidden')) as observed, \
             patch('backend.m03_integration.call_adapter', side_effect=AssertionError('Wrong configured unit')) as adapter:
            with self.assertRaises(EvaluationError) as error:
                generate_recorded(self.root, self.config, dict(self.request, dataset_id=context['dataset_id']))
        observed.assert_not_called()
        adapter.assert_not_called()
        _, receipt = self.stored(error.exception.origin_generation_id)
        self.assertEqual(receipt['status'], 'ERROR')
        self.assertEqual(receipt['dataset_id'], context['dataset_id'])

    def test_evaluation_truth_in_snapshot_is_rejected_before_generation_or_receipt(self):
        self.snapshot['evaluation_only'] = True
        self.path.write_bytes(encoded(self.snapshot))
        self.config['m03_real_generator']['snapshot_sha256'] = sha(self.path.read_bytes())
        before = self.path.read_bytes()
        with patch('backend.m03_real_generator.generate_observed') as observed:
            with self.assertRaises(EvaluationError):
                generate_recorded(self.root, self.config, self.request)
        observed.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / 'results/m03_generations').exists())

    def test_snapshot_change_after_start_is_detected_and_failed_origin_is_preserved(self):
        original_sha = sha(self.path.read_bytes())
        def changed(root, config, request):
            starts = list((self.root / 'results/m03_generations').glob('*/started.json'))
            self.assertEqual(len(starts), 1)
            self.assertEqual(json.loads(starts[0].read_bytes())['analysis_input']['snapshot_sha256'], original_sha)
            changed_snapshot = deepcopy(self.snapshot)
            changed_snapshot['processes'][0]['business_steps'][0]['target'] = 'Different synthetic target'
            self.path.write_bytes(encoded(changed_snapshot))
            return dict(self.response(), source_snapshot_sha256=sha(self.path.read_bytes()))
        with patch('backend.m03_real_generator.generate_observed', side_effect=changed):
            with self.assertRaises(EvaluationError) as error:
                generate_recorded(self.root, self.config, self.request)
        folder, receipt = self.stored(error.exception.origin_generation_id)
        self.assertEqual(receipt['status'], 'ERROR')
        self.assertEqual(receipt['analysis_input']['snapshot_sha256'], original_sha)
        self.assertNotEqual(sha(self.path.read_bytes()), original_sha)
        self.assertFalse((folder / 'response.json').exists())

    def test_legacy_id_only_adapter_has_a_nonofficial_receipt_without_fabricated_inputs(self):
        config = dict(adapters=dict(scenario_generation=['SYNTHETIC-NEVER-SPAWN']))
        with patch('backend.m03_integration._real_input', side_effect=AssertionError('No feature contract configured')), \
             patch('backend.m03_integration.call_adapter', return_value=self.response()) as adapter:
            result = generate_recorded(self.root, config, self.request)
        sent = adapter.call_args.args[2]
        self.assertEqual(sent, {key: self.request[key] for key in ('business_unit_id', 'workflow_id')})
        _, receipt = self.stored(result['origin_generation_id'])
        self.assertIsNone(receipt['analysis_input'])
        self.assertIsNone(receipt['dataset'])
        self.assertEqual(receipt['run_mode'], 'DEVELOPMENT')
        self.assertIsNone(result['official_pass'])
        with patch('backend.m03_integration.call_adapter') as adapter:
            with self.assertRaises(EvaluationError):
                generate_recorded(self.root, config, dict(self.request, run_mode='OFFICIAL', dataset_id='SYNTHETIC'))
        adapter.assert_not_called()

    def test_presence_of_feature_contract_or_scoped_observed_binding_prevents_legacy_bypass(self):
        configurations = [dict(adapters=dict(scenario_generation=['SYNTHETIC']), m03=dict(generator_mode='MOCK')),
                          dict(self.config, adapters=dict(scenario_generation=['SYNTHETIC']))]
        for config in configurations:
            with self.subTest(feature_present='m03' in config), \
                 patch('backend.m03_integration.call_adapter') as adapter, \
                 patch('backend.m03_real_generator.generate_observed') as observed:
                with self.assertRaises(EvaluationError):
                    generate_recorded(self.root, config, dict(self.request, dataset_id=None))
                adapter.assert_not_called()
                observed.assert_not_called()

    def test_wire_enum_type_messages_and_malformed_module_responses_are_structured(self):
        for field in ('run_mode', 'generator_mode'):
            for value in ([], {}, None, True, 7):
                with self.subTest(field=field, value_type=type(value).__name__), self.assertRaises(EvaluationError) as error:
                    generate_recorded(self.root, self.config, dict(self.request, **{field: value}))
                self.assertEqual(str(error.exception), f'Invalid type for {field}: expected string')
        with self.assertRaises(EvaluationError) as error:
            generate_recorded(self.root, self.config, dict(self.request, generator_mode='INVALID'))
        self.assertEqual(str(error.exception), 'Invalid generator mode')
        for response in ([], None, dict(self.response(), status=[])):
            with self.subTest(response_type=type(response).__name__), \
                 patch('backend.m03_real_generator.generate_observed', return_value=response):
                with self.assertRaises(EvaluationError):
                    generate(self.root, self.config, self.request)


if __name__ == '__main__':
    unittest.main()
