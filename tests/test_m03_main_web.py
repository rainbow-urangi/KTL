"""Synthetic M03 transport regressions. No network, model, browser, or old-score reuse."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import m03_main_web as bridge
from backend.evaluators import EvaluationError, METRICS
from backend.m03_provenance import encoded, generate_recorded
from backend.server import Service


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(root, name, raw):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


class M03MainWebTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No external network')))
        self.enterContext(patch('urllib.request.urlopen', side_effect=AssertionError('No provider request')))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No model/browser process')))

    def fixture(self, root):
        selection = [dict(business_unit_id='SYN-' + str(index), name='Synthetic ' + str(index),
            mapping=dict(workflow_id='W' + str(index), source_event_ids_outside_execution_window=[]),
            source_execution_status='COMPLETED') for index in range(10)]
        candidate = dict(candidate_id='SYNTHETIC-FROZEN', business_unit_ids=[x['business_unit_id'] for x in selection],
                         selection=selection)
        processes = [dict(canonical_instance_id='W' + str(index), source_process_id='P' + str(index),
            business_steps=[dict(step_order=1, action_type='NAVIGATE', target='/synthetic-' + str(index),
                generated_step_id='STEP-' + str(index), source_event_ids=['SYN-E' + str(index)],
                source_node_ids=['SYN-N' + str(index)], resolution_status='UNRESOLVED' if index == 0 else 'RESOLVED')])
            for index in range(10)]
        snapshot_raw, candidate_raw = encoded(dict(processes=processes)), encoded(candidate)
        snapshot_name = 'results/development/synthetic-observed/business_steps.json'
        binding = dict(snapshot_path=snapshot_name, snapshot_sha256=sha(snapshot_raw))
        archive_source = b"raise RuntimeError('This archived module must never be imported')\n"
        frozen = dict(candidate_ids=candidate['business_unit_ids'], candidate_sha256=sha(candidate_raw),
            generator_version='SYNTHETIC-observed-v1', binding=binding,
            result=dict(success=9, failure=1, total=10, success_rate=90, target=80),
            sha256={snapshot_name:sha(snapshot_raw), bridge.CANDIDATE:sha(candidate_raw),
                'backend/m03_integration.py':sha(archive_source), 'backend/server.py':'0' * 64})
        freeze_raw = encoded(frozen)
        self.enterContext(patch.object(bridge, 'FREEZE_HASH', sha(freeze_raw)))
        bundle = root / bridge.BUNDLE
        put(bundle, bridge.FREEZE, freeze_raw)
        put(bundle, snapshot_name, snapshot_raw)
        put(bundle, bridge.CANDIDATE, candidate_raw)
        put(bundle, 'backend/m03_integration.py', archive_source)
        put(bundle, 'backend/server.py', b'SYNTHETIC transport exception\n')
        put(root, snapshot_name, snapshot_raw)
        put(root, bridge.INPUTS + '/business_steps.json', snapshot_raw)
        put(root, bridge.INPUTS + '/candidate.json', candidate_raw)
        put(root, bridge.INPUT_MANIFEST, bridge._manifest_bytes(frozen))
        config = dict(targets={metric:80 if metric == 'M03' else None for metric in METRICS},
            m03_real_generator=binding, m03=dict(generator_mode='REAL', business_units=[
                dict(business_unit_id='FEATURE-ONLY', workflow_id='FEATURE-WORKFLOW')]),
            integration_datasets={})
        put(root, 'backend/config.json', encoded(config))
        return config, frozen, candidate

    def test_catalog_never_generates_and_does_not_need_a_historical_score(self):
        from backend.measurement_ui import catalog
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = Service(root)
            service.config = lambda: dict(targets={metric:None for metric in METRICS})
            for status in ('READY', 'BLOCKED'):
                with self.subTest(status=status):
                    ready = dict(status=status, dataset_id=bridge.DATASET, details=dict(total_scenarios=10,
                        business_units=[dict(business_unit_id='SYN-' + str(i), name='Synthetic') for i in range(10)]))
                    with patch.object(bridge, 'generate_recorded', side_effect=AssertionError('GET cannot generate')), \
                            patch.object(bridge, 'readiness', return_value=ready), \
                            patch('backend.m05_main_web.readiness', return_value=dict(status='BLOCKED', details={})), \
                            patch('backend.m06_candidate.prepare', return_value=dict(status='BLOCKED', details={})):
                        item = next(x for x in catalog(service)['metrics'] if x['metric_id'] == 'M03')
                    self.assertEqual(item['execution_available'], status == 'READY')
                    self.assertEqual(len(item['details']['business_units']), 10)
                    self.assertIsNone(item['latest'])
                    self.assertFalse((root / 'results').exists())

    def test_dispatch_calls_only_the_explicit_development_batch(self):
        service = Service()
        with patch.object(bridge, 'run', return_value={'ok':True}) as run:
            self.assertEqual(service.run('M03', 'DEVELOPMENT', bridge.DATASET), {'ok':True})
            for mode in ('OFFICIAL', 'REFERENCE'):
                with self.assertRaises(EvaluationError):
                    service.run('M03', mode, bridge.DATASET)
            self.assertEqual(run.call_count, 1)

    def test_missing_bundle_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(bridge.readiness(Path(temp))['status'], 'BLOCKED')

    def test_readiness_checks_bytes_without_writes_generation_or_old_runtime_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            before = {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(bridge, 'generate_recorded', side_effect=AssertionError('Readiness cannot generate')):
                self.assertEqual(bridge.readiness(root)['status'], 'READY')
            self.assertEqual(before, {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertFalse((root / 'results/m03_generations').exists())

    def test_only_original_server_exception_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            put(root / bridge.BUNDLE, 'backend/server.py', b'CHANGED transport bytes allowed by original exception')
            self.assertEqual(bridge.readiness(root)['status'], 'READY')
            put(root / bridge.BUNDLE, 'backend/m03_integration.py', b'CHANGED archived evaluator')
            with patch.object(bridge, 'generate_recorded') as generate, patch.object(bridge, 'save_run') as ingest:
                self.assertEqual(bridge.readiness(root)['status'], 'BLOCKED')
                with self.assertRaises(EvaluationError):
                    bridge.run(root, json.loads((root / 'backend/config.json').read_bytes()))
            generate.assert_not_called()
            ingest.assert_not_called()

    def test_freeze_candidate_active_snapshot_and_staged_inputs_are_all_hash_bound(self):
        paths = [bridge.BUNDLE + '/' + bridge.FREEZE, bridge.BUNDLE + '/' + bridge.CANDIDATE,
                 'results/development/synthetic-observed/business_steps.json',
                 bridge.INPUTS + '/business_steps.json', bridge.INPUTS + '/candidate.json', bridge.INPUT_MANIFEST]
        for name in paths:
            with self.subTest(path=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                config, _, _ = self.fixture(root)
                path = root / name
                path.write_bytes(path.read_bytes() + b' ')
                with patch.object(bridge, 'generate_recorded') as generate, patch.object(bridge, 'save_run') as ingest:
                    with self.assertRaises(EvaluationError):
                        bridge.run(root, config)
                generate.assert_not_called()
                ingest.assert_not_called()

    def test_all_ten_real_receipts_restore_main_structure_ratio_without_claiming_order_evaluation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config, frozen, _ = self.fixture(root)
            before_config = deepcopy(config)
            before_snapshot = (root / frozen['binding']['snapshot_path']).read_bytes()
            first = bridge.run(root, config)
            second = bridge.run(root, config)
            self.assertEqual(config, before_config)
            self.assertEqual((root / frozen['binding']['snapshot_path']).read_bytes(), before_snapshot)
            self.assertNotEqual(first['run_id'], second['run_id'])
            self.assertEqual(first['score'], 90)
            self.assertIs(first['threshold_met'], True)
            self.assertIsNone(first['official_pass'])
            self.assertEqual(first['sample_count'], 10)
            details = first['details']
            self.assertEqual(details['evaluation_status'], 'COMPLETED')
            self.assertEqual(details['success_policy'], 'MAIN_COMPAT_STRUCTURE')
            self.assertEqual(details['raw_counts']['successful_scenario_count'], 9)
            self.assertEqual((details['total_scenarios'], details['success'], details['failure']), (10, 9, 1))
            self.assertIs(details['reference_order_evaluated'], False)
            self.assertEqual(details['order_evaluation'], dict(status='NOT_EVALUATED', score=None))
            summary = details['generation_summary']
            self.assertEqual((summary['attempt_count'], summary['successful_count'], summary['failed_count']), (10, 9, 1))
            self.assertFalse(summary['model_inference_executed'])
            self.assertFalse(details['historical_score_used'])
            rows = details['rows']
            self.assertIs(rows[0]['success'], False)
            self.assertTrue(all(row['success'] is True for row in rows[1:]))
            for row in rows:
                for key in ('schema_valid', 'step_order_valid', 'action_present', 'target_present', 'generated_steps',
                            'failure_reason', 'generator_version', 'source_snapshot_sha256', 'source_process_id'):
                    self.assertIn(key, row)
            self.assertEqual(len(list((root / 'results/m03_generations').glob('*/receipt.json'))), 20)
            payload = json.loads((root / 'results/development' / first['run_id'] / 'received_payload.json').read_bytes())
            self.assertEqual(len(payload['scenarios']), 10)
            for scenario in payload['scenarios']:
                folder = root / 'results/m03_generations' / scenario['origin_generation_id']
                receipt = json.loads((folder / 'receipt.json').read_bytes())
                self.assertEqual(receipt['analysis_input']['snapshot_sha256'], frozen['binding']['snapshot_sha256'])
                self.assertEqual(receipt['response_sha256'], sha((folder / 'response.json').read_bytes()))
                self.assertEqual(json.loads((folder / 'response.json').read_bytes()), scenario)
                self.assertFalse(scenario['official'])
            self.assertEqual(details['generation_provenance']['classification'], 'POSTHOC_REEVALUATION')
            self.assertFalse(details['generation_provenance']['official_eligible'])

    def test_no_truth_or_archive_result_enters_the_generator_and_feature_config_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config, _, _ = self.fixture(root)
            with patch.object(bridge, 'generate_recorded', wraps=generate_recorded) as generate:
                bridge.run(root, config)
            for call in generate.call_args_list:
                self.assertEqual(set(call.args[2]), {'business_unit_id','workflow_id','generator_mode','run_mode'})
                self.assertEqual(call.args[1]['m03'], config['m03'])
                self.assertNotIn('reference', call.args[2])
                self.assertNotIn('historical_score', call.args[2])
            self.assertNotIn(bridge.DATASET, config['integration_datasets'])

    def test_canonical_unit_or_registry_conflicts_fail_before_any_generation(self):
        for conflict in ('canonical', 'registry', 'binding'):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                config, _, _ = self.fixture(root)
                if conflict == 'canonical':
                    config['m03']['business_units'].append(dict(business_unit_id='SYN-0', workflow_id='W0'))
                elif conflict == 'registry':
                    config['integration_datasets'][bridge.DATASET] = dict(manifest='different.json', run_mode='OFFICIAL')
                else:
                    config['m03_real_generator']['snapshot_sha256'] = '0' * 64
                put(root, 'backend/config.json', encoded(config))
                with patch.object(bridge, 'generate_recorded') as generate, patch.object(bridge, 'save_run') as ingest:
                    with self.assertRaises(EvaluationError):
                        bridge.run(root, config)
                generate.assert_not_called()
                ingest.assert_not_called()

    def test_transport_error_is_retained_in_the_ten_unit_denominator_without_fabricating_a_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config, _, _ = self.fixture(root)
            def generate(path, settings, request):
                if request['business_unit_id'] == 'SYN-1':
                    raise EvaluationError('SYNTHETIC failed provider transport', 'ERROR')
                return generate_recorded(path, settings, request)
            with patch.object(bridge, 'generate_recorded', side_effect=generate) as calls:
                result = bridge.run(root, config)
            self.assertEqual(calls.call_count, 10)
            self.assertEqual(result['sample_count'], 10)
            self.assertEqual(result['score'], 80)
            self.assertIs(result['details']['rows'][1]['success'], False)
            summary = result['details']['generation_summary']
            self.assertEqual((summary['successful_count'], summary['failed_count']), (8, 2))
            origin = result['details']['generation_provenance']['origins'][1]
            self.assertEqual(origin['reason'], 'NO_SERVER_GENERATION_RECEIPT')
            self.assertEqual(len(list((root / 'results/m03_generations').glob('*/receipt.json'))), 9)

    def test_input_tamper_after_generation_prevents_any_result_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config, _, _ = self.fixture(root)
            def generate(path, settings, request):
                response = generate_recorded(path, settings, request)
                if request['business_unit_id'] == 'SYN-9':
                    put(root, bridge.INPUTS + '/business_steps.json', b'CHANGED after generation')
                return response
            with patch.object(bridge, 'generate_recorded', side_effect=generate), patch.object(bridge, 'save_run') as ingest:
                with self.assertRaises(EvaluationError):
                    bridge.run(root, config)
            ingest.assert_not_called()
            self.assertEqual(len(list((root / 'results/m03_generations').glob('*/receipt.json'))), 10)
            self.assertFalse((root / 'results/development/latest-M03.json').exists())

    def test_receipt_response_tamper_is_rejected_before_compatibility_result_publication(self):
        from backend.m03_provenance import assess_origins
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config, _, _ = self.fixture(root)
            def corrupt_then_assess(path, payload, reference, hashes, manifest_sha):
                origin = payload['scenarios'][0]['origin_generation_id']
                source = root / 'results/m03_generations' / origin / 'response.json'
                source.write_bytes(source.read_bytes() + b' ')
                return assess_origins(path, payload, reference, hashes, manifest_sha)
            with patch.object(bridge, 'assess_origins', side_effect=corrupt_then_assess):
                with self.assertRaises(EvaluationError):
                    bridge.run(root, config)
            self.assertFalse((root / 'results/development/latest-M03.json').exists())


if __name__ == '__main__':
    unittest.main()
