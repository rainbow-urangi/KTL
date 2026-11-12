"""Malformed JSON types must yield structured HTTP errors, not disconnects."""
import copy
import json
import unittest
from unittest.mock import patch
from tests import test_integration_sandbox as sandbox


class ApiInputValidationTests(unittest.TestCase):
    setUp = sandbox.IntegrationSandboxTests.setUp
    tearDown = sandbox.IntegrationSandboxTests.tearDown
    request = sandbox.IntegrationSandboxTests.request
    malformed = ([], {}, True, False, None, 1, 1.5)

    def assert_error(self, endpoint, payload):
        status, raw = self.request('POST', endpoint, payload)
        body = json.loads(raw)
        self.assertEqual(status, 422, body)
        self.assertEqual(body['status'], 'ERROR')
        self.assertIsInstance(body['error'], str)
        self.assertNotIn('score', body)

    def test_generate_enum_types_and_values(self):
        good = dict(business_unit_id='BU03', workflow_id='WF-001')
        for field in ('run_mode', 'generator_mode'):
            for value in (*self.malformed, '', 'invalid'):
                with self.subTest(field=field, value=value):
                    self.assert_error('/api/m03/generate', dict(good, **{field:value}))
        status, raw = self.request('POST', '/api/m03/generate', good)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['status'], 'SUCCESS')

    def test_integration_run_mode_types(self):
        for sample in self.samples:
            for value in (*self.malformed, 'invalid'):
                with self.subTest(metric=sample['metric_id'], value=value):
                    payload = copy.deepcopy(sample['request'])
                    payload['run_mode'] = value
                    self.assert_error(sample['endpoint'], payload)

    def test_case_status_types_and_values(self):
        for sample in self.samples:
            metric = sample['metric_id']
            if metric not in ('M04', 'M07'):
                continue
            fields = ('status',) if metric == 'M04' else ('generation_status','syntax_status','execution_status','final_status')
            for field in fields:
                for value in (*self.malformed, '', 'invalid'):
                    with self.subTest(metric=metric, field=field, value=value):
                        payload = copy.deepcopy(sample['request'])
                        if metric == 'M04':
                            payload['cases'] = [dict(case_id=f'C{i}', status='PASS' if i < 9 else 'FAIL') for i in range(10)]
                        payload['cases'][0][field] = value
                        self.assert_error(sample['endpoint'], payload)

    def test_malformed_generator_response_is_structured(self):
        # Adapter results are external input too; exercise the configured-adapter branch.
        request = dict(business_unit_id='BU03', workflow_id='WF-001', generator_mode='REAL')
        for value in self.malformed:
            result = dict(business_unit_id='BU03', workflow_id='WF-001', scenario_id='S1', steps=[], status=value)
            with patch('backend.m03_integration.call_adapter', return_value=result):
                self.assert_error('/api/m03/generate', request)

    def test_normal_contract_and_retry(self):
        sandbox.IntegrationSandboxTests.test_all_samples_real_http_counts_and_official_null(self)

    def test_nonobject_payloads_are_structured(self):
        for endpoint in ['/api/m03/generate', *(s['endpoint'] for s in self.samples)]:
            for value in ([], True, 1, 'invalid'):
                with self.subTest(endpoint=endpoint, value=value):
                    self.assert_error(endpoint, value)

