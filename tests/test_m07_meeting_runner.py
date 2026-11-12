"""Temporary synthetic meeting-run integration; never calls a real model or browser.

The manager, original snapshots, archives, syntax checks and central result storage
run normally. Only the external generator and Selenium worker are synthetic.
"""
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from backend.evaluators import EvaluationError
from backend.m07 import generator, meeting
from backend.m07.store import M07Manager
from backend.session import RuntimeSession


MODEL = 'SYNTHETIC-MEETING-MODEL'
STAMP = '2030-01-01T00:00:00+00:00'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inputs():
    rows = []
    for number in range(1, 21):
        identity = 'SYNTHETIC-MEETING-' + str(number).zfill(2)
        path = '/synthetic/' + str(number).zfill(2)
        url = 'https://synthetic.example.invalid' + path
        rows.append(dict(input_id='SYNTHETIC-INPUT-' + str(number).zfill(2), scenario=dict(
            scenario_id=identity, scenario_name='SYNTHETIC temporary case ' + str(number),
            business_unit_id='SYNTHETIC-BU-' + str(number), workflow_id='SYNTHETIC-WF-' + str(number),
            steps=[dict(order=1, action='open', target='SYNTHETIC business screen', url=url,
                        expected_result='SYNTHETIC case route is displayed')],
            execution_contract=dict(version=1, scenario_id=identity, steps=[
                dict(order=1, action='open', target=dict(url=url),
                     checks=[dict(kind='url_path', expected=path)])]))))
    return dict(items=rows)


def synthetic_code(scenario):
    return ('# 합성 테스트 원본, 실행하지 않음\r\n'
            'from selenium import webdriver\r\n'
            'SCENARIO_ID = ' + repr(scenario['scenario_id']) + '\r\n'
            'def synthetic_browser_assert(driver):\r\n'
            '    assert driver.current_url.endswith(' + repr(scenario['steps'][0]['url'].split('.invalid')[1]) + ')\r\n')


def http_failure(status=500):
    response = dict(http_status=status, body_policy='HASH_ONLY', diagnostics=dict(
        error_type='server_error' if status != 429 else 'tokens',
        error_code='server_error' if status != 429 else 'rate_limit_exceeded',
        numeric_headers={'retry-after': 60} if status == 429 else {}))
    return generator.GenerationError('SYNTHETIC HTTP failure', dict(
        http_request_attempted=True, provider_response_observed=True, response=response,
        model=MODEL, requested_model=MODEL, prompt_version=generator.MEETING_PROMPT_VERSION,
        request_id='req_SyntheticFailure'))


class SynchronousMeetingManager(M07Manager):
    """Use the production exception/lock lifecycle with synchronous scheduling."""
    def _launch(self, identity, phase, run_lock, browser_lock=None):
        self._active = identity
        self._work(identity, phase, run_lock, browser_lock)

    def _run_case(self, job, case):
        self.synthetic_runs.append(case['scenario_id'])
        failed = case['scenario_id'] in self.synthetic_execution_failures
        status = 'FAIL' if failed else 'PASS'
        case.update(status=status, started_at=STAMP, completed_at=STAMP,
                    browser_started=True, business_step_complete=not failed,
                    independent_checks_passed=not failed,
                    error='SYNTHETIC browser assertion failed' if failed else None,
                    steps=[dict(sequence=1, action='open', target='SYNTHETIC business screen',
                                expected_result='SYNTHETIC case route is displayed', status=status,
                                started_at=STAMP, completed_at=STAMP,
                                independent_checks_passed=not failed)])


class MeetingRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-m07-meeting-runner-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.enterContext(patch.dict(os.environ, {key: '' for key in (
            'OPENAI_API_KEY', 'KTL_M07_OPENAI_API_KEY', 'KTL_M07_MODEL',
            'KTL_M04_RBEM_USERNAME', 'KTL_M04_RBEM_PASSWORD')}))
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No test network')))
        self.enterContext(patch('urllib.request.urlopen', side_effect=AssertionError('No test HTTP/LLM')))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No test subprocess/browser')))
        # Runtime env has an empty model by design; inject this synthetic model via
        # the existing settings boundary rather than reading the user's secrets.
        self.enterContext(patch('backend.m07.store.settings', return_value=dict(
            api_key='', model=MODEL, target_url='https://synthetic.example.invalid/login')))
        self.config = dict(targets=dict(M07=80), m07=dict(model=MODEL, model_display_name='SYNTHETIC LLM'), m04={})
        self.calls, self.responses, self.behavior = [], {}, {}
        self.expected_input = inputs()
        self.code_factory = synthetic_code
        self.manager = SynchronousMeetingManager(self.root, lambda: deepcopy(self.config),
                                                 generator=self.provider, session=RuntimeSession())
        self.manager.synthetic_runs = []
        self.manager.synthetic_execution_failures = set()
        self.manager._readiness = lambda: dict(selenium=True, chrome=True, edge=False, message='SYNTHETIC ONLY')
        self.enterContext(patch.object(self.manager, '_evaluate', side_effect=AssertionError('No legacy denominator')))

    def provider(self, root, config, scenario):
        self.assertEqual(Path(root), self.root)
        self.assertIs(scenario.get('meeting_protocol'), True)
        for key in ('code', 'prepared_code', 'code_source', 'generated_by_llm', 'm03_run_id', 'score', 'ground_truth'):
            self.assertNotIn(key, scenario)
        folder = self.manager.execution_directory / self.manager._active
        frozen = json.loads((folder / 'meeting_inputs.json').read_bytes())
        self.assertEqual(frozen, self.expected_input)
        stored = json.loads((folder / 'execution.json').read_bytes())
        self.assertEqual(len(stored['cases']), 20)
        self.assertEqual(digest((folder / 'meeting_inputs.json').read_bytes()), stored['meeting_inputs_sha256'])
        self.assertEqual(len(list(folder.glob('CASE-*/meeting_input.json'))), 20)
        identity = scenario['scenario_id']
        source = next(item['scenario'] for item in frozen['items'] if item['scenario']['scenario_id'] == identity)
        self.assertEqual({key: value for key, value in scenario.items() if key != 'meeting_protocol'}, source)
        self.assertNotIn('meeting_protocol', source)
        self.calls.append(deepcopy(scenario))
        failure = self.behavior.get(identity)
        if isinstance(failure, Exception):
            raise failure
        instructions, text = generator.prompt(scenario, config)
        code = self.code_factory(scenario)
        response = dict(id='resp_Synthetic_' + str(len(self.calls)), model=MODEL, status='completed',
                        output=[dict(type='message', content=[dict(type='output_text', text=code)])])
        raw = (json.dumps(response, ensure_ascii=False) + '\r\n').encode('utf-8')
        value = dict(code=code, response=response, response_bytes=raw, instructions=instructions, input=text,
                     requested_model=MODEL, model=MODEL, request_id='req_Synthetic_' + str(len(self.calls)),
                     generated_by_llm=True, http_request_attempted=True, provider_response_observed=True,
                     prompt_version=generator.MEETING_PROMPT_VERSION)
        self.responses[identity] = deepcopy(value)
        return value

    def create(self):
        job = self.manager.create_meeting(deepcopy(self.expected_input))['generation']
        result = self.manager.read(job['generation_id'])['generation']
        self.assertEqual(result['status'], 'GENERATED', result.get('error'))
        return result

    def validate(self, job):
        self.manager.validate(job['generation_id'])
        return self.manager.read(job['generation_id'])['generation']

    def folder(self, job):
        return self.manager.execution_directory / job['generation_id']

    def test_twenty_frozen_inputs_generate_twenty_originals_before_separate_inspection(self):
        job = self.create()
        self.assertEqual(len(self.calls), 20)
        self.assertEqual(self.manager.synthetic_runs, [])
        self.assertEqual(job['counts']['generated_code_count'], 20)
        self.assertEqual(job['counts']['both_pass_count'], 0)
        self.assertIsNone(job['result'])
        self.assertTrue(job['meeting_protocol'])
        self.assertEqual(job['measurement_protocol'], 'M07_MEETING_20_V1')
        self.assertEqual(job['code_source'], 'LLM')
        self.assertEqual(job['measurement']['denominator'], 20)
        self.assertEqual(job['measurement']['evaluation_status'], 'PENDING')
        self.assertFalse((self.root / 'results').exists())
        folder = self.folder(job)
        raw_archive = (folder / 'code.zip').read_bytes()
        self.assertEqual(digest(raw_archive), job['archive_sha256'])
        with zipfile.ZipFile(folder / 'code.zip') as archive:
            self.assertEqual(json.loads(archive.read('meeting_inputs.json')), self.expected_input)
            scripts = [name for name in archive.namelist() if name.endswith('/script.py')]
            self.assertEqual(len(scripts), 20)
            for case, row in zip(job['cases'], self.expected_input['items']):
                self.assertEqual(case['input_id'], row['input_id'])
                self.assertEqual(case['source_kind'], 'MEETING_SCENARIO_INPUT')
                self.assertIsNone(case['source_m03_run_id'])
                self.assertFalse(case['source_synthetic'])
                self.assertIs(case['generated_by_llm'], True)
                self.assertEqual(case['model'], MODEL)
                prefix = case['case_id'] + '/'
                for name in ('meeting_input.json', 'source_scenario.json', 'execution_scenario.json',
                             'execution_contract.json', 'script.py', 'prompt.json', 'response.json'):
                    self.assertEqual(archive.read(prefix + name), (folder / prefix / name).read_bytes())
                self.assertEqual(json.loads(archive.read(prefix + 'meeting_input.json')), row)
                self.assertEqual(json.loads(archive.read(prefix + 'source_scenario.json')), row['scenario'])
                self.assertNotIn('meeting_protocol', json.loads(archive.read(prefix + 'execution_scenario.json')))
                expected = self.responses[case['scenario_id']]
                self.assertEqual(archive.read(prefix + 'response.json'), expected['response_bytes'])
                self.assertEqual(archive.read(prefix + 'script.py'), expected['code'].encode('utf-8'))
                shown = self.manager.code(job['generation_id'], case['case_id'])
                self.assertEqual(shown['code'], expected['code'])
                self.assertEqual(base64.b64decode(shown['code_base64']), expected['code'].encode('utf-8'))
                self.assertEqual(shown['identity_verification'], dict(
                    verified=True, source_sha256=case['code_sha256'], display_sha256=case['code_sha256']))
                self.assertNotIn(prefix + 'prepared_code.py', archive.namelist())

    def test_sixteen_pass_three_execution_fail_one_generation_error_is_eighty_of_twenty(self):
        identities = [row['scenario']['scenario_id'] for row in self.expected_input['items']]
        self.manager.synthetic_execution_failures = set(identities[16:19])
        self.behavior[identities[19]] = http_failure()
        generated = self.create()
        self.assertEqual(generated['counts']['generated_code_count'], 19)
        archive_before = (self.folder(generated) / 'code.zip').read_bytes()
        done = self.validate(generated)
        self.assertEqual(done['status'], 'COMPLETED', done.get('error'))
        self.assertEqual(len(self.calls), 20)
        self.assertEqual(len(self.manager.synthetic_runs), 19)
        self.assertEqual(done['counts'], dict(generation_request_count=20, generated_code_count=19,
                                             syntax_pass_count=19, execution_pass_count=16, both_pass_count=16))
        self.assertEqual([case['final_status'] for case in done['cases']], ['PASS'] * 16 + ['FAIL'] * 4)
        self.assertEqual(done['measurement']['integrated_percent'], 80)
        self.assertEqual(done['measurement']['syntax_percent'], 95)
        self.assertEqual(done['measurement']['provider_http_attempt_count'], 20)
        self.assertEqual(done['result_scope'], 'MEETING_FIXED_20')
        self.assertNotIn('legacy_result', done)
        result = done['result']
        self.assertEqual(result['score'], 80)
        self.assertEqual(result['sample_count'], 20)
        self.assertTrue(result['threshold_met'])
        self.assertIsNone(result['official_pass'])
        self.assertEqual(result['details']['denominator'], 20)
        self.assertEqual(result['details']['formula'], 'both_pass_count / 20 * 100')
        self.assertEqual(len(result['details']['rows']), 20)
        self.assertEqual((self.folder(done) / 'code.zip').read_bytes(), archive_before)
        stored_folder = self.root / 'results/development' / result['run_id']
        self.assertEqual(json.loads((stored_folder / 'result.json').read_bytes()), result)
        self.assertEqual(json.loads((stored_folder / 'received_payload.json').read_bytes())['counts']['generated_code_count'], 19)
        self.assertEqual(json.loads((self.root / 'results/development/latest-M07.json').read_bytes())['score'], 80)
        for relative, expected_hash in result['input_sha256'].items():
            self.assertEqual(digest((self.root / relative).read_bytes()), expected_hash)
        for case in done['cases'][:19]:
            self.assertEqual(case['validation_code_sha256'], case['code_sha256'])
        with self.assertRaises(EvaluationError):
            self.manager.validate(done['generation_id'])

    def test_twenty_observed_http_failures_complete_as_zero_with_all_twenty_retained(self):
        for row in self.expected_input['items']:
            self.behavior[row['scenario']['scenario_id']] = http_failure()
        done = self.validate(self.create())
        self.assertEqual(done['status'], 'COMPLETED', done.get('error'))
        self.assertEqual(len(self.calls), 20)
        self.assertEqual(self.manager.synthetic_runs, [])
        self.assertEqual(done['measurement']['provider_http_attempt_count'], 20)
        self.assertEqual(done['measurement']['provider_response_count'], 20)
        self.assertEqual(done['measurement']['evaluation_status'], 'COMPLETED')
        self.assertEqual(done['measurement']['integrated_percent'], 0)
        self.assertEqual(done['result']['score'], 0)
        self.assertEqual(done['result']['sample_count'], 20)
        self.assertFalse(done['result']['threshold_met'])
        self.assertIsNone(done['result']['official_pass'])
        self.assertEqual([case['final_status'] for case in done['cases']], ['FAIL'] * 20)
        with zipfile.ZipFile(self.folder(done) / 'code.zip') as archive:
            self.assertEqual(len([name for name in archive.namelist() if name.endswith('/meeting_input.json')]), 20)
            self.assertFalse(any(name.endswith('/script.py') for name in archive.namelist()))

    def test_429_stops_unattempted_inputs_and_keeps_partial_result_not_ready(self):
        self.behavior[self.expected_input['items'][2]['scenario']['scenario_id']] = http_failure(429)
        done = self.validate(self.create())
        self.assertEqual(done['status'], 'COMPLETED')
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len(self.manager.synthetic_runs), 2)
        self.assertEqual(done['measurement']['provider_http_attempt_count'], 3)
        self.assertEqual(done['measurement']['not_attempted_count'], 17)
        self.assertEqual(done['measurement']['evaluation_status'], 'NOT_READY')
        self.assertEqual(done['counts']['both_pass_count'], 2)
        for field in ('generation_percent', 'syntax_percent', 'integrated_percent', 'browser_percent'):
            self.assertIsNone(done['measurement'][field])
        self.assertIsNone(done['result'])
        self.assertEqual([case['generation_status'] for case in done['cases']], ['PASS', 'PASS', 'ERROR'] + ['SKIPPED'] * 17)
        folder = self.folder(done)
        for case in done['cases'][3:]:
            self.assertIs(case['generation_invoked'], False)
            self.assertIs(case['generation_http_attempted'], False)
            for name in ('script.py', 'prompt.json', 'response.json'):
                self.assertFalse((folder / case['case_id'] / name).exists())
        self.assertFalse((self.root / 'results/development/latest-M07.json').exists())
        self.assertTrue(done['provider_state']['blocked'])
        with self.assertRaises(EvaluationError):
            self.manager.create_meeting(deepcopy(self.expected_input))
        self.assertEqual(len(self.calls), 3)

    def test_unknown_http_attempt_does_not_become_a_zero_or_nineteen_case_score(self):
        self.behavior[self.expected_input['items'][-1]['scenario']['scenario_id']] = EvaluationError('SYNTHETIC unknown transport')
        done = self.validate(self.create())
        self.assertEqual(done['measurement']['provider_http_attempt_count'], 19)
        self.assertEqual(done['measurement']['provider_http_unknown_count'], 1)
        self.assertEqual(done['measurement']['evaluation_status'], 'NOT_READY')
        self.assertEqual(done['counts']['both_pass_count'], 19)
        self.assertIsNone(done['measurement']['integrated_percent'])
        self.assertIsNone(done['result'])
        self.assertFalse((self.root / 'results/development/latest-M07.json').exists())

    def test_changed_input_code_or_contract_refuses_display_and_inspection_before_browser(self):
        for name in ('meeting_inputs.json', 'meeting_input.json', 'source_scenario.json', 'script.py', 'execution_contract.json'):
            with self.subTest(name=name):
                job = self.create()
                folder = self.folder(job)
                path = folder / name if name == 'meeting_inputs.json' else folder / job['cases'][0]['case_id'] / name
                path.write_bytes(path.read_bytes() + b'\n')
                before_runs = len(self.manager.synthetic_runs)
                with self.assertRaises(EvaluationError):
                    self.manager.code(job['generation_id'], job['cases'][0]['case_id'])
                done = self.validate(job)
                self.assertEqual(done['status'], 'ERROR')
                self.assertIn('SHA-256', done['error'])
                self.assertIsNone(done['result'])
                self.assertEqual(len(self.manager.synthetic_runs), before_runs)
        self.assertFalse((self.root / 'results/development/latest-M07.json').exists())

    def test_top_level_literal_scenario_identity_is_required_and_original_code_is_preserved(self):
        invalid = {}
        for number, item in enumerate(self.expected_input['items'][:4], 1):
            scenario = item['scenario']
            identity = scenario['scenario_id']
            prefix = 'from selenium import webdriver\n'
            declarations = [
                'def nested_only():\n    SCENARIO_ID = ' + repr(identity) + '\n',
                'SCENARIO_ID = "SYNTHETIC-WRONG"\n',
                'SCENARIO_ID = "".join([' + repr(identity) + '])\n',
                '# SCENARIO_ID = ' + repr(identity) + '\n']
            invalid[identity] = prefix + declarations[number - 1] + 'assert webdriver is not None\n'
        self.code_factory = lambda scenario: invalid.get(scenario['scenario_id'], synthetic_code(scenario))
        generated = self.create()
        done = self.validate(generated)
        self.assertEqual(done['status'], 'COMPLETED', done.get('error'))
        self.assertEqual(done['counts']['generated_code_count'], 20)
        self.assertEqual(done['counts']['syntax_pass_count'], 20)
        self.assertEqual(done['counts']['execution_pass_count'], 16)
        self.assertEqual(done['result']['score'], 80)
        self.assertTrue(set(invalid).isdisjoint(self.manager.synthetic_runs))
        for case in done['cases'][:4]:
            self.assertEqual(case['execution_status'], 'SKIPPED')
            self.assertEqual(case['final_status'], 'FAIL')
            self.assertIn('SCENARIO_ID', case['error'])
            shown = self.manager.code(done['generation_id'], case['case_id'])
            self.assertEqual(shown['code'], invalid[case['scenario_id']])
            self.assertTrue(shown['identity_verification']['verified'])

    def test_incorrect_validation_hash_or_archive_hash_never_produces_a_result(self):
        for field in ('code_sha256', 'archive_sha256'):
            with self.subTest(field=field):
                job = self.create()
                path = self.manager._job_path(job['generation_id'])
                stored = json.loads(path.read_bytes())
                if field == 'code_sha256':
                    stored['cases'][0][field] = '0' * 64
                else:
                    stored[field] = '0' * 64
                path.write_text(json.dumps(stored), encoding='utf-8')
                before_runs = len(self.manager.synthetic_runs)
                done = self.validate(job)
                self.assertEqual(done['status'], 'ERROR')
                self.assertIsNone(done['result'])
                self.assertEqual(len(self.manager.synthetic_runs), before_runs)
        self.assertFalse((self.root / 'results/development/latest-M07.json').exists())


if __name__ == '__main__':
    unittest.main()
