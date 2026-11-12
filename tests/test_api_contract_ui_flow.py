"""합의된 네 API의 임시 loopback 회귀. 실제 모델·GPT·업무 실행 증빙이 아니다."""
import base64
from copy import deepcopy
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from backend.server import LocalHTTPServer, ROOT, Service, make_handler


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ApiContractUiFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-four-api-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = dict(
            targets={f'M0{i}': value for i, value in enumerate((65, 75, 80, 90, .79, 1, 80), 1)},
            adapters={}, official_manifests={}, adapter_timeout_seconds=5,
            integration_datasets={}, m03=dict(generator_mode='MOCK'),
            m03_evaluation_references={}, m04={}, m07={},
        )
        (self.root / 'backend').mkdir()
        shutil.copytree(ROOT / 'frontend', self.root / 'frontend')
        self.external_directory = self.root / 'data/evaluation/synthetic-api-results'
        self.external_directory.mkdir(parents=True)
        input_path = self.external_directory / 'input.csv'
        input_path.write_bytes(b'event_id\nSYNTHETIC-EXTERNAL-EVENT\n')
        self.external_manifest = self.external_directory / 'data_manifest.json'
        self.external_manifest.write_bytes(encoded(dict(
            dataset_id='synthetic-api-results', run_mode='DEVELOPMENT', official=False,
            synthetic=True, data_class='DEVELOPMENT',
            purpose='SYNTHETIC_API_TEST_ONLY_NOT_EXECUTION_OR_PERFORMANCE_EVIDENCE',
            files=[dict(path='input.csv', sha256=sha(input_path.read_bytes()))],
        )))
        self.config['integration_datasets']['synthetic-api-results'] = dict(
            manifest=self.external_manifest.relative_to(self.root).as_posix(), run_mode='DEVELOPMENT')
        self.save_config()
        # The web flow must never silently run either uploaded CSV inference or
        # the existing M02/M06 model. One routing test explicitly simulates the
        # old runner with a mock; none of these guards executes an actual model.
        self.analysis_guards = [self.enterContext(patch(name, side_effect=AssertionError(
            'CSV inference is outside the four API contract'))) for name in (
                'backend.uploaded_analysis.analyze_upload',
                'backend.uploaded_analysis._run_inference',
                'backend.upload_pipeline.UploadPipeline.analyze',
        )]
        self.model = self.enterContext(patch('backend.model_runner.EvaluationModelRunner.run',
            side_effect=AssertionError('Real model forward is forbidden in this regression')))
        self.provider = self.enterContext(patch('backend.m07.generator.urllib.request.urlopen',
            side_effect=AssertionError('Real GPT calls are forbidden in this regression')))
        self.process = self.enterContext(patch('subprocess.Popen',
            side_effect=AssertionError('No script, browser, or subprocess may execute')))
        self.service = Service(self.root, session_scoped=True)
        self.server = LocalHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop)

    def tearDown(self):
        for guard in self.analysis_guards:
            guard.assert_not_called()
        self.provider.assert_not_called()
        self.process.assert_not_called()

    def save_config(self):
        (self.root / 'backend/config.json').write_bytes(encoded(self.config))

    def stop(self):
        self.server.shutdown()
        self.worker.join(timeout=5)
        self.server.server_close()

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            body = None if payload is None else encoded(payload)
            connection.request(method, path, body, {} if body is None else {'Content-Type': 'application/json'})
            reply = connection.getresponse()
            raw = reply.read()
            value = json.loads(raw) if 'application/json' in reply.getheader('Content-Type', '') else raw
            return reply.status, value, dict(reply.getheaders())
        finally:
            connection.close()

    def context(self):
        status, context, _ = self.request('GET', '/api/development/m03/context')
        self.assertEqual(status, 200, context)
        return context

    def envelope(self, metric, *, context=None, **content):
        return dict(external_run_id='SYNTHETIC-' + metric + '-' + uuid.uuid4().hex,
                    dataset_id=context['dataset_id'] if context else 'synthetic-api-results',
                    run_mode='DEVELOPMENT',
                    source_module=context['source_module'] if context else 'synthetic-external-producer',
                    source_version=context['source_version'] if context else 'SYNTHETIC-1',
                    submitted_at=datetime.now(timezone.utc).isoformat(),
                    dataset_manifest_sha256=context['dataset_manifest_sha256'] if context
                        else sha(self.external_manifest.read_bytes()),
                    details=dict(synthetic=context['synthetic'] if context else True,
                                 test_only=True, execution_not_performed=True), **content)

    def generated_and_ingested(self):
        context = self.context()
        unit = context['business_units'][0]
        status, scenario, _ = self.request('POST', '/api/m03/generate',
            dict(unit, run_mode='DEVELOPMENT', generator_mode='MOCK', dataset_id=context['dataset_id']))
        self.assertEqual(status, 200, scenario)
        self.assertTrue(scenario['synthetic'])
        self.assertEqual(scenario['generator_mode'], 'MOCK')
        self.assertIn('origin_generation_id', scenario)
        payload = self.envelope('M03', context=context, scenarios=[scenario])
        status, result, _ = self.request('POST', '/api/integrations/m03/result', payload)
        self.assertEqual(status, 201, result)
        return scenario, payload, result

    def test_generate_ingest_history_and_fixed_script_preserve_the_original_snapshots(self):
        scenario, payload, result = self.generated_and_ingested()
        self.assertIsNone(result['score'])
        self.assertIsNone(result['official_pass'])
        self.assertEqual(result['details']['evaluation_status'], 'NOT_READY')
        for filename, expected in (('received_payload.json', payload), ('result.json', result)):
            path = f'/api/evaluations/m03/runs/{result["run_id"]}/{filename}'
            status, stored, _ = self.request('GET', path)
            self.assertEqual(status, 200)
            self.assertEqual(stored, expected)
        status, state, _ = self.request('GET', f'/api/development/m03/runs/{result["run_id"]}/scenarios')
        self.assertEqual(status, 200)
        self.assertEqual(state['scenarios'], [scenario])
        status, history, _ = self.request('GET', '/api/development/m03/runs')
        self.assertEqual(status, 200)
        self.assertIn(result['run_id'], [row['run_id'] for row in history['runs']])

        # Storage/AST compatibility only: this legacy-trace fixture is never
        # executed, and the independent external result below does not claim it ran.
        raw = ('# SYNTHETIC STORAGE ONLY; NEVER EXECUTED\nfrom selenium import webdriver\n'
               f'SCENARIO_ID = {scenario["scenario_id"]!r}\nassert SCENARIO_ID\n').encode()
        status, registration, _ = self.request('POST', '/api/development/m04/scripts', dict(
            filename='synthetic-storage-only.py', scenario_id=scenario['scenario_id'],
            m03_run_id=result['run_id'], python_base64=base64.b64encode(raw).decode()))
        self.assertEqual(status, 201, registration)
        metadata = registration['script']
        self.assertEqual(metadata['sha256'], sha(raw))
        self.assertEqual(metadata['source_m03_run_id'], result['run_id'])
        self.assertFalse(metadata['business_step_required'])
        self.assertEqual(metadata['step_evidence_mode'], 'LEGACY_TRACE')
        folder = self.root / 'data/development/m04_runner/scripts' / metadata['script_id']
        self.assertEqual((folder / 'script.py').read_bytes(), raw)
        self.assertEqual(json.loads((folder / 'source_scenario.json').read_bytes()), scenario)
        self.assertEqual(metadata['source_scenario_sha256'], sha((folder / 'source_scenario.json').read_bytes()))
        status, scripts, _ = self.request('GET', '/api/development/m04/scripts')
        self.assertEqual(status, 200)
        self.assertEqual([row['script_id'] for row in scripts['scripts']], [metadata['script_id']])
        self.assertEqual(self.request('GET', '/api/development/m04/executions')[1]['executions'], [])

    def test_real_generation_facade_uses_the_configured_adapter_and_preserves_its_response(self):
        path = self.external_directory / 'analysis_manifest.json'
        path.write_bytes(encoded(dict(dataset_id='SYNTHETIC-ANALYSIS', synthetic=False,
            workflow_ids=['SYNTHETIC-WF'], files=[dict(path='input.csv',
                sha256=sha((self.external_directory / 'input.csv').read_bytes()))])))
        definition = dict(business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF',
                          business_name='Synthetic API fixture', start_screen='Synthetic start',
                          end_condition='Synthetic end', required_procedures=['Synthetic original step'])
        self.config['m03'] = dict(generator_mode='REAL', transport='SUBPROCESS', business_units=[definition],
            source_module='synthetic-test-adapter', source_version='SYNTHETIC-1',
            input_manifest=path.relative_to(self.root).as_posix())
        self.config['adapters']['scenario_generation'] = ['SYNTHETIC_TEST_ONLY_NEVER_EXECUTE']
        self.save_config()
        context = self.context()
        original = dict(business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF',
            scenario_id='SYNTHETIC-ADAPTER-SCENARIO', status='SUCCESS',
            steps=[dict(order=1, action='click', target='#synthetic-original', evidence=['SYNTHETIC-E'])],
            producer_extension=dict(original=True), official=False, data_class='DEVELOPMENT')
        with patch('backend.m03_integration.call_adapter', return_value=deepcopy(original)) as adapter:
            status, response, _ = self.request('POST', '/api/m03/generate', dict(
                context['business_units'][0], generator_mode='REAL', run_mode='DEVELOPMENT',
                dataset_id=context['dataset_id']))
        self.assertEqual(status, 200, response)
        adapter.assert_called_once()
        args = adapter.call_args.args
        self.assertEqual(args[1], 'scenario_generation')
        self.assertEqual(args[2]['business_definition'], definition)
        self.assertEqual(args[2]['analysis_input'], context['verified_input'])
        self.assertNotIn('reference', args[2])
        for key, value in original.items():
            self.assertEqual(response[key], value)
        self.assertEqual(response['generator_mode'], 'REAL')
        self.assertFalse(response['synthetic'])
        self.model.assert_not_called()

    def test_external_m03_original_is_not_rewritten_and_failed_items_stay_in_the_total(self):
        passed = dict(business_unit_id='SYNTHETIC-GOOD', workflow_id='SYNTHETIC-WF-GOOD',
            scenario_id='SYNTHETIC-EXTERNAL-GOOD', status='SUCCESS',
            steps=[dict(order=1, action='open', target='https://example.invalid/synthetic')],
            producer_extension=dict(opaque_original=['preserved', 3]))
        failed = dict(business_unit_id='SYNTHETIC-FAILED', workflow_id='SYNTHETIC-WF-FAILED',
            scenario_id='SYNTHETIC-EXTERNAL-FAILED', status='FAILED', steps=[],
            producer_error_code='SYNTHETIC_GENERATION_FAILURE')
        payload = self.envelope('M03', scenarios=[passed, failed])
        original = deepcopy(payload)
        status, result, _ = self.request('POST', '/api/integrations/m03/result', payload)
        self.assertEqual(status, 201, result)
        self.assertEqual(result['sample_count'], 2)
        self.assertEqual(result['details']['total_scenario_count'], 2)
        self.assertEqual(result['details']['evaluation_status'], 'NOT_READY')
        self.assertIsNone(result['score'])
        self.assertIsNone(result['details']['successful_scenario_count'])
        self.assertIsNone(result['details']['rows'][0]['success'])
        self.assertFalse(result['details']['rows'][1]['success'])
        status, stored, _ = self.request('GET',
            f'/api/evaluations/m03/runs/{result["run_id"]}/received_payload.json')
        self.assertEqual(status, 200)
        self.assertEqual(stored, original)

    def test_external_m04_and_m07_results_use_the_registered_denominator_and_remain_nonofficial(self):
        definitions = dict(
            M04=dict(total_execution_count=2, successful_execution_count=1, failed_execution_count=1),
            M07=dict(generation_request_count=2, generated_code_count=2, syntax_pass_count=2,
                     execution_pass_count=1, both_pass_count=1),
        )
        for metric, counts in definitions.items():
            with self.subTest(metric=metric):
                payload = self.envelope(metric, counts=counts)
                status, result, _ = self.request('POST', f'/api/integrations/{metric.lower()}/result', payload)
                self.assertEqual(status, 201, result)
                self.assertEqual(result['sample_count'], 2)
                self.assertEqual(result['score'], 50)
                self.assertIsNone(result['official_pass'])
                self.assertEqual(result['details']['raw_counts'], counts)
                self.assertEqual(self.request('GET', result['result_file'])[1], result)
                status, evidence, _ = self.request('GET', result['evidence_file'])
                self.assertEqual(status, 200)
                self.assertIsInstance(evidence, bytes)
                self.assertTrue(evidence)
                status, catalog, _ = self.request('GET', '/api/evaluations?mode=DEVELOPMENT')
                self.assertEqual(status, 200)
                row = next(row for row in catalog['metrics'] if row['metric_id'] == metric)
                self.assertEqual(row['latest'], result)
        self.assertEqual(self.request('GET', '/api/development/m04/executions')[1]['executions'], [])

    def test_duplicate_external_id_and_wrong_manifest_hash_do_not_create_another_result(self):
        payload = self.envelope('M04', counts=dict(total_execution_count=2, successful_execution_count=1))
        status, result, _ = self.request('POST', '/api/integrations/m04/result', payload)
        self.assertEqual(status, 201, result)
        self.assertEqual(self.request('POST', '/api/integrations/m04/result', payload)[0], 409)
        bad = dict(payload, external_run_id='SYNTHETIC-BAD-' + uuid.uuid4().hex, dataset_manifest_sha256='0' * 64)
        self.assertEqual(self.request('POST', '/api/integrations/m04/result', bad)[0], 422)
        self.assertEqual(len(list((self.root / 'results/development').glob('DEV-M04-*'))), 1)

    def test_removed_upload_analysis_routes_are_404_and_never_infer(self):
        for method, path, payload in (
            ('GET', '/api/development/pipeline?csv_dataset_id=' + 'a' * 32, None),
            ('POST', '/api/development/m03/analyze-upload?csv_dataset_id=' + 'a' * 32, {}),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.request(method, path, payload)[0], 404)
        self.assertFalse(hasattr(self.service, 'upload_pipeline'))
        self.assertFalse((self.root / 'data/development/uploaded_analysis').exists())

    def test_m02_and_m06_run_keep_their_original_runner_and_do_not_consume_csv_scope(self):
        self.model.side_effect = None
        self.model.return_value = dict(run_id='SYNTHETIC-LEGACY-MODEL', test_only=True)
        returned = {metric: dict(metric_id=metric, run_id='SYNTHETIC-' + metric,
            run_mode='DEVELOPMENT', status='SYNTHETIC_ROUTING_ONLY', score=None)
            for metric in ('M02', 'M06')}
        with patch('backend.model_runner.evaluation.evaluate_run', return_value=returned) as evaluate:
            for metric in ('M02', 'M06'):
                status, result, _ = self.request('POST',
                    f'/api/evaluations/{metric.lower()}/run?mode=DEVELOPMENT&csv_dataset_id=' + 'a' * 32)
                self.assertEqual(status, 200, result)
                self.assertEqual(result, returned[metric])
            self.assertEqual(evaluate.call_count, 2)
            for call in evaluate.call_args_list:
                self.assertEqual(call.args[2], self.model.return_value)
        self.assertEqual(self.model.call_count, 2, 'Mock calls prove routing only, not a model execution')
        self.assertFalse((self.root / 'data/development/uploaded_analysis').exists())

    def test_m02_m06_catalog_is_unchanged_by_csv_query_and_gets_never_generate(self):
        status, baseline, _ = self.request('GET', '/api/evaluations?mode=DEVELOPMENT')
        self.assertEqual(status, 200)
        status, scoped, _ = self.request('GET',
            '/api/evaluations?mode=DEVELOPMENT&csv_dataset_id=' + 'a' * 32 + '&analysis_id=UPLOAD-ANALYSIS-' + 'b' * 32)
        self.assertEqual(status, 200)
        self.assertEqual(scoped, baseline)
        for _ in range(2):
            self.assertEqual(self.request('GET', '/api/development/m03/context')[0], 200)
            self.assertEqual(self.request('GET', '/api/development/m03/runs')[1]['runs'], [])
        self.model.assert_not_called()
        self.assertFalse((self.root / 'results/m03_generations').exists())

    def test_mock_cannot_claim_official_generation_or_evaluation(self):
        status, body, _ = self.request('POST', '/api/m03/generate', dict(
            business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF',
            run_mode='OFFICIAL', generator_mode='MOCK'))
        self.assertEqual(status, 422, body)
        payload = self.envelope('M04', counts=dict(total_execution_count=2, successful_execution_count=2))
        payload['run_mode'] = 'OFFICIAL'
        self.assertEqual(self.request('POST', '/api/integrations/m04/result', payload)[0], 422)
        self.assertFalse((self.root / 'results/official').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
