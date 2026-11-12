"""2026-11-12 wire-contract audit. Isolated synthetic fixtures, no production runs."""
import copy
import json
import test_integration_sandbox as sandbox


class JuniorAPIContractTests(sandbox.IntegrationSandboxTests):
    # Existing harness starts a temporary server with isolated results/data/config.
    def test_required_metadata_and_type_errors_all_result_routes(self):
        for sample in self.samples:
            for field in ('external_run_id', 'dataset_id', 'source_module', 'source_version',
                          'submitted_at', 'dataset_manifest_sha256'):
                for value in (None, 1, [], {}):
                    payload = copy.deepcopy(sample['request'])
                    payload[field] = value
                    status, raw = self.request('POST', sample['endpoint'], payload)
                    self.assertEqual(status, 422, (sample['metric_id'], field, value, raw))
                    body = json.loads(raw)
                    self.assertEqual(body['status'], 'ERROR')
                    self.assertIn('error', body)
                    self.assertNotIn('score', body)

    def test_generation_schema_retry_and_invalid_fields(self):
        payload = {'business_unit_id': 'BU03', 'workflow_id': 'WF-001'}
        status, raw = self.request('POST', '/api/m03/generate', payload)
        result = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertTrue({'business_unit_id', 'workflow_id', 'scenario_id', 'status', 'steps',
                         'run_mode', 'generator_mode', 'synthetic', 'official_pass'} <= result.keys())
        for step in result['steps']:
            self.assertTrue({'order', 'action', 'target'} <= step.keys())
        self.assertEqual(self.request('POST', '/api/m03/generate', payload)[1], raw)
        for field in payload:
            bad = dict(payload); del bad[field]
            self.assertEqual(self.request('POST', '/api/m03/generate', bad)[0], 422)
            bad[field] = 10
            self.assertEqual(self.request('POST', '/api/m03/generate', bad)[0], 422)
        for extra in ({'unknown': 1}, {'run_mode': 'INVALID'}, {'generator_mode': 'INVALID'}):
            self.assertEqual(self.request('POST', '/api/m03/generate', dict(payload, **extra))[0], 422)

    def test_results_central_score_response_and_duplicate_contract(self):
        for sample in self.samples:
            payload = copy.deepcopy(sample['request']); payload['score'] = -1234
            payload['external_run_id'] += '-contract'
            status, raw = self.request('POST', sample['endpoint'], payload)
            result = json.loads(raw)
            self.assertEqual(status, 201, result)
            self.assertEqual(result['score'], {'M03': 80, 'M04': 90, 'M07': 80}[sample['metric_id']])
            self.assertTrue({'run_id', 'metric_id', 'score', 'sample_count', 'target', 'threshold_met',
                             'official_pass', 'pass', 'details', 'evidence_file', 'provenance',
                             'evaluator_version', 'input_sha256'} <= result.keys())
            self.assertIsNone(result['official_pass'])
            self.assertTrue(result['threshold_met'])
            self.assertEqual(self.request('GET', result['evidence_file'])[0], 200)
            status, raw = self.request('POST', sample['endpoint'], payload)
            self.assertEqual(status, 409)
            self.assertEqual(json.loads(raw)['status'], 'DUPLICATE_EXTERNAL_RUN')

    def test_boolean_counts_and_missing_cases_contract(self):
        for sample in self.samples:
            p = copy.deepcopy(sample['request'])
            if sample['metric_id'] == 'M03':
                p['scenarios'] = 'not-an-array'
            else:
                p['counts'][next(iter(p['counts']))] = True
            self.assertEqual(self.request('POST', sample['endpoint'], p)[0], 422)
        # Compatibility: M04 count-only is accepted, not silently promoted to case-required.
        p = copy.deepcopy(next(s['request'] for s in self.samples if s['metric_id'] == 'M04'))
        p.pop('cases', None)
        self.assertEqual(self.request('POST', '/api/integrations/m04/result', p)[0], 201)
