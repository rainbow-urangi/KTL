"""Offline checks of fixed existing code; all source files are synthetic.

Only a temporary loopback server is used. No generated program is imported or
executed, and provider, browser, historical results and product data stay intact.
"""
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.m07 import generator
from backend.m07.existing import DATASET, ExistingCodeCheck
from backend.server import LocalHTTPServer, ROOT, Service, make_handler


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class ExistingFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-existing-code-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.bundle = self.root / DATASET
        self.bundle.mkdir(parents=True)
        self.manifest = dict(schema_version='m07-existing-code-batch-v1', code_source='EXISTING_LLM',
                             source_generation_id='M07-GEN-' + 'a' * 32, required_count=10, cases=[])
        self.raw_codes = {}
        for number in range(1, 11):
            case_id = f'CASE-{number:03d}'
            identity = f'SYNTHETIC-EXISTING-{number:02d}'
            workflow = f'CU{number:02d}'
            scenario = dict(scenario_id=identity, scenario_name='Synthetic existing problem ' + str(number),
                            workflow_id=workflow, business_unit_id=workflow,
                            steps=[dict(order=1, action='open', target='Synthetic problem screen',
                                        expected_result='Synthetic page path is displayed')])
            contract = dict(version=1, scenario_id=identity, steps=[dict(order=1, action='open',
                target=dict(url='https://synthetic.example.invalid/existing/' + str(number)),
                checks=[dict(kind='url_path', expected='/existing/' + str(number))])])
            # Missing imports, top-level raise and function side effects cannot
            # affect a syntax-only result. One valid case deliberately has no ID.
            code = (('# synthetic original bytes\r\n' +
                    (f'SCENARIO_ID = {identity!r}\r\n' if number != 6 else '') +
                    'import deliberately_missing_existing_code_dependency\r\n' +
                    "raise RuntimeError('This program must never execute')\r\n" +
                    'def body_never_called():\r\n    return unknown_synthetic_symbol()\r\n').encode('utf-8'))
            if number in {9, 10}:
                code = b'def syntactically_broken(:\r\n'
            values = {'code': ('script.py', code), 'scenario': ('source_scenario.json', encoded(scenario)),
                      'contract': ('execution_contract.json', encoded(contract))}
            row = dict(case_id=case_id, scenario_id=identity, workflow_id=workflow, expected_syntax_status='PASS')
            for kind, (filename, raw) in values.items():
                path = f'{case_id}/{filename}'
                target = self.bundle / path
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(raw)
                row[kind + '_path'] = path
                row[kind + '_sha256'] = digest(raw)
            self.raw_codes[case_id] = code
            self.manifest['cases'].append(row)
        self.write_manifest()
        self.latest = self.root / 'data/development/m07_existing_checks/latest.json'
        self.protected = {}
        for relative in ('data/development/m07_codes/generations/OLD/execution.json',
                         'data/development/m07_codes/provider_state.json',
                         'results/development/latest-M07.json'):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = encoded(dict(synthetic_historical_record=relative, unchanged=True))
            target.write_bytes(raw)
            self.protected[relative] = raw
        self.transport = self.enterContext(patch.object(generator.urllib.request, 'urlopen',
            side_effect=AssertionError('Existing code checks must not call a provider')))
        self.generate = self.enterContext(patch.object(generator, 'generate',
            side_effect=AssertionError('Existing code checks must not generate code')))
        self.process = self.enterContext(patch.object(subprocess, 'Popen',
            side_effect=AssertionError('Existing code checks must not run code or a browser')))

    def tearDown(self):
        self.transport.assert_not_called()
        self.generate.assert_not_called()
        self.process.assert_not_called()
        for relative, raw in self.protected.items():
            self.assertEqual((self.root / relative).read_bytes(), raw, relative)

    def write_manifest(self):
        raw = encoded(self.manifest)
        (self.bundle / 'manifest.json').write_bytes(raw)
        self.manifest_sha = digest(raw)

    def checker(self):
        return ExistingCodeCheck(self.root, manifest_sha256=self.manifest_sha)

    def result(self, value):
        # The API may return the refreshed context or the result itself. In both
        # forms the stored, reloaded context must carry the identical result.
        return value['result'] if 'result' in value else value


class ExistingCodeTests(ExistingFixture):
    def test_context_returns_exact_problem_expected_conditions_and_code_without_writing(self):
        context = self.checker().context()
        self.assertEqual(context['code_source'], 'EXISTING_LLM')
        self.assertEqual(context['source_generation_id'], self.manifest['source_generation_id'])
        self.assertEqual(context['required_count'], 10)
        self.assertEqual(context['target'], 80)
        self.assertIsNone(context['result'])
        self.assertEqual(len(context['cases']), 10)
        self.assertFalse(self.latest.exists())
        for shown, source in zip(context['cases'], self.manifest['cases']):
            self.assertEqual(shown['case_id'], source['case_id'])
            self.assertEqual(shown['scenario_id'], source['scenario_id'])
            self.assertEqual(shown['code'].encode('utf-8'), self.raw_codes[source['case_id']])
            self.assertEqual(shown['code_sha256'], source['code_sha256'])
            self.assertEqual(shown['problem'], json.loads((self.bundle / source['scenario_path']).read_bytes()))
            self.assertEqual(shown['expected_results'], json.loads((self.bundle / source['contract_path']).read_bytes())['steps'])

    def test_eight_valid_two_invalid_is_eighty_without_import_execution_or_browser(self):
        checker = self.checker()
        with patch.dict(sys.modules, {'selenium': None, 'deliberately_missing_existing_code_dependency': None}):
            result = self.result(checker.validate())
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(result['score'], 80)
        self.assertEqual(result['sample_count'], 10)
        self.assertEqual(result['syntax_pass_count'], 8)
        self.assertEqual(result['syntax_fail_count'], 2)
        self.assertIsNone(result['official_pass'])
        self.assertTrue(result['checked_at'])
        self.assertEqual([row['syntax_status'] for row in result['cases']], ['PASS'] * 8 + ['FAIL'] * 2)
        self.assertEqual([row['matches_expected'] for row in result['cases']], [True] * 8 + [False] * 2)
        self.assertEqual(checker.context()['result'], result)
        for row in result['cases'][8:]:
            self.assertTrue(row['error'])
            self.assertNotIn('def syntactically_broken', row['error'])

    def test_matching_a_historical_expected_failure_does_not_turn_syntax_failure_into_pass(self):
        self.manifest['cases'][8]['expected_syntax_status'] = 'FAIL'
        self.write_manifest()
        result = self.result(self.checker().validate())
        self.assertEqual(result['score'], 80)
        ninth = result['cases'][8]
        self.assertEqual(ninth['syntax_status'], 'FAIL')
        self.assertEqual(ninth['expected_syntax_status'], 'FAIL')
        self.assertTrue(ninth['matches_expected'])
        self.assertFalse(result['cases'][9]['matches_expected'])

    def test_result_reload_is_stable_and_does_not_rewrite_source_or_historical_records(self):
        originals = {p.relative_to(self.bundle).as_posix(): p.read_bytes()
                     for p in self.bundle.rglob('*') if p.is_file()}
        result = self.result(self.checker().validate())
        saved = self.latest.read_bytes()
        self.assertEqual(self.checker().context()['result'], result)
        self.assertEqual(self.latest.read_bytes(), saved)
        self.assertEqual({p.relative_to(self.bundle).as_posix(): p.read_bytes()
                          for p in self.bundle.rglob('*') if p.is_file()}, originals)

    def test_code_problem_or_contract_tampering_is_rejected_before_a_result_write(self):
        for kind in ('code', 'scenario', 'contract'):
            with self.subTest(source_kind=kind):
                path = self.bundle / self.manifest['cases'][0][kind + '_path']
                raw = path.read_bytes()
                try:
                    path.write_bytes(raw + b'\n')
                    with self.assertRaises(EvaluationError):
                        self.checker().context()
                    with self.assertRaises(EvaluationError):
                        self.checker().validate()
                    self.assertFalse(self.latest.exists())
                finally:
                    path.write_bytes(raw)

    def test_manifest_tampering_or_incomplete_batch_is_rejected_without_a_result(self):
        checker = self.checker()
        self.manifest['cases'][0]['expected_syntax_status'] = 'FAIL'
        self.write_manifest()
        with self.assertRaises(EvaluationError):
            checker.validate()
        self.assertFalse(self.latest.exists())
        self.manifest['cases'].pop()
        self.write_manifest()
        with self.assertRaises(EvaluationError):
            self.checker().validate()
        self.assertFalse(self.latest.exists())

    def test_source_tampering_after_a_check_cannot_overwrite_or_return_the_saved_score(self):
        self.checker().validate()
        saved = self.latest.read_bytes()
        path = self.bundle / self.manifest['cases'][0]['code_path']
        path.write_bytes(path.read_bytes() + b'# synthetic tampering\n')
        with self.assertRaises(EvaluationError):
            self.checker().context()
        with self.assertRaises(EvaluationError):
            self.checker().validate()
        self.assertEqual(self.latest.read_bytes(), saved)


class ExistingCodeApiTests(ExistingFixture):
    def setUp(self):
        super().setUp()
        (self.root / 'backend').mkdir()
        shutil.copytree(ROOT / 'frontend', self.root / 'frontend')
        (self.root / 'backend/config.json').write_bytes(encoded(dict(
            targets={f'M0{i}': value for i, value in enumerate((65, 75, 80, 90, .79, 1, 80), 1)},
            adapters={}, official_manifests={}, integration_datasets={}, m03=dict(generator_mode='MOCK'), m04={}, m07={})))
        self.service = Service(self.root, session_scoped=True)
        self.service._m07_existing = self.checker()
        self.legacy = self.enterContext(patch.object(self.service, 'm07',
            side_effect=AssertionError('Local existing-code routes must not initialize a generation manager')))
        self.server = LocalHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def request(self, method, path, payload=None, *, raw=None, headers=None):
        body = raw if raw is not None else None if payload is None else encoded(payload)
        request_headers = dict(headers or {})
        if body is not None and 'Content-Type' not in request_headers:
            request_headers['Content-Type'] = 'application/json'
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            client.request(method, path, body, request_headers)
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def test_loopback_get_validate_reload_uses_only_local_sources_and_keeps_old_m07_untouched(self):
        endpoint = '/api/development/m07/existing-codes'
        status, before = self.request('GET', endpoint)
        self.assertEqual(status, 200, before)
        self.assertIsNone(before['result'])
        status, checked = self.request('POST', endpoint + '/validate', {})
        self.assertEqual(status, 200, checked)
        result = self.result(checked)
        self.assertEqual(result['score'], 80)
        self.assertEqual(result['sample_count'], 10)
        self.assertIsNone(result['official_pass'])
        status, reloaded = self.request('GET', endpoint)
        self.assertEqual(status, 200, reloaded)
        self.assertEqual(reloaded['result'], result)
        self.legacy.assert_not_called()

    def test_loopback_rejects_foreign_origin_nonempty_duplicate_or_nonfinite_json(self):
        endpoint = '/api/development/m07/existing-codes/validate'
        for raw, expected_status in ((b'{"unexpected":true}', 422),
                                     (b'{"x":1,"x":2}', 400), (b'{"x":NaN}', 400)):
            with self.subTest(raw=raw):
                status, error = self.request('POST', endpoint, raw=raw)
                self.assertEqual(status, expected_status, error)
                self.assertFalse(self.latest.exists())
        status, error = self.request('POST', endpoint, {}, headers={'Content-Type': 'text/plain'})
        self.assertEqual(status, 422, error)
        self.assertFalse(self.latest.exists())
        status, error = self.request('POST', endpoint, {}, headers={'Origin': 'https://foreign.example.invalid'})
        self.assertEqual(status, 403, error)
        self.assertFalse(self.latest.exists())
        self.legacy.assert_not_called()

    def test_stale_server_sources_reject_before_creating_a_local_check(self):
        with patch.object(self.service, 'require_current_sources',
                          side_effect=EvaluationError('Synthetic stale source', 'RESTART_REQUIRED')) as guard:
            status, error = self.request('POST', '/api/development/m07/existing-codes/validate', {})
        self.assertEqual(status, 409, error)
        self.assertEqual(error['status'], 'RESTART_REQUIRED')
        guard.assert_called_once()
        self.assertFalse(self.latest.exists())
        self.legacy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
