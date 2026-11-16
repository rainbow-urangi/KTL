"""Opt-in M07 orchestration with temporary synthetic inputs and blocked I/O.

The real manager fixes inputs, preserves provider bytes, checks Python syntax,
holds production locks and stores results. Provider and browser workers below
are synthetic; these tests are not official or real-browser evidence.
"""
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
from backend.m04.store import _RunLock
from backend.m07 import generator
from backend.m07.store import M07Manager
from backend.session import RuntimeSession
from tests.test_m07_meeting_runner import MODEL, inputs, synthetic_code, http_failure


STAMP = '2030-01-01T00:00:00+00:00'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class SynchronousOneClickManager(M07Manager):
    def _launch(self, identity, phase, run_lock, browser_lock=None):
        self.launches.append(phase)
        self._active = identity
        self._work(identity, phase, run_lock, browser_lock)

    def _run_case(self, job, case):
        self.synthetic_runs.append(case['scenario_id'])
        failed = case['scenario_id'] in self.synthetic_failures
        status = 'FAIL' if failed else 'PASS'
        case.update(status=status, started_at=STAMP, completed_at=STAMP,
                    browser_started=True, business_step_complete=not failed,
                    independent_checks_passed=not failed,
                    error='SYNTHETIC assertion failure' if failed else None,
                    steps=[dict(sequence=1, action='open', target='SYNTHETIC screen',
                                expected_result='SYNTHETIC expected route', status=status,
                                independent_checks_passed=not failed)])


class OneClickMeetingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ktl-m07-one-click-synthetic-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.enterContext(patch.dict(os.environ, {key: '' for key in (
            'OPENAI_API_KEY', 'KTL_M07_OPENAI_API_KEY', 'KTL_M07_MODEL',
            'KTL_M04_RBEM_USERNAME', 'KTL_M04_RBEM_PASSWORD')}))
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No test network')))
        self.enterContext(patch('urllib.request.urlopen', side_effect=AssertionError('No test HTTP/provider')))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No test subprocess/browser')))
        self.enterContext(patch('backend.m07.store.settings', return_value=dict(
            api_key='', model=MODEL, target_url='https://synthetic.example.invalid/login')))
        self.config = dict(targets=dict(M07=80), m07=dict(model=MODEL), m04={})
        self.payload = inputs()
        self.original_payload = deepcopy(self.payload)
        self.calls = []
        self.responses = {}
        self.behavior = {}
        self.code_factory = synthetic_code
        self.provider_probe = None
        self.manager = SynchronousOneClickManager(
            self.root, lambda: deepcopy(self.config), generator=self.provider, session=RuntimeSession())
        self.manager.launches = []
        self.manager.synthetic_runs = []
        self.manager.synthetic_failures = set()
        self.manager._readiness = lambda: dict(selenium=True, chrome=True, edge=False, message='SYNTHETIC ONLY')
        self.enterContext(patch.object(self.manager, '_evaluate', side_effect=AssertionError('No legacy denominator')))

    def provider(self, root, config, scenario):
        self.assertEqual(Path(root), self.root)
        self.assertIs(scenario.get('meeting_protocol'), True)
        for name in ('code', 'prepared_code', 'score', 'ground_truth', 'm03_run_id'):
            self.assertNotIn(name, scenario)
        folder = self.manager.execution_directory / self.manager._active
        self.assertEqual(json.loads((folder / 'meeting_inputs.json').read_bytes()), self.payload)
        self.assertEqual(len(list(folder.glob('CASE-*/meeting_input.json'))), 20)
        self.calls.append(scenario['scenario_id'])
        if len(self.calls) == 1 and self.provider_probe is not None:
            self.provider_probe()
        failure = self.behavior.get(scenario['scenario_id'])
        if isinstance(failure, Exception):
            raise failure
        instructions, text = generator.prompt(scenario, config)
        code = self.code_factory(scenario)
        response = dict(id='resp_Synthetic', model=MODEL, status='completed', output=[dict(
            type='message', content=[dict(type='output_text', text=code)])])
        raw = (json.dumps(response, ensure_ascii=False) + '\r\n').encode('utf-8')
        self.responses[scenario['scenario_id']] = dict(code=code.encode('utf-8'), response=raw)
        return dict(code=code, response=response, response_bytes=raw, instructions=instructions, input=text,
                    requested_model=MODEL, model=MODEL, request_id='req_SyntheticOneClick',
                    generated_by_llm=True, http_request_attempted=True, provider_response_observed=True,
                    prompt_version=generator.MEETING_PROMPT_VERSION)

    def create(self, **kwargs):
        value = self.manager.create_meeting(self.payload, **kwargs)['generation']
        self.assertEqual(self.payload, self.original_payload)
        return self.manager.read(value['generation_id'])['generation']

    def automatic(self):
        return self.create(auto_validate=True)

    def folder(self, job):
        return self.manager.execution_directory / job['generation_id']

    def assert_not_ready(self, job):
        self.assertEqual(job['measurement']['evaluation_status'], 'NOT_READY')
        self.assertIsNone(job['measurement']['integrated_percent'])
        self.assertIsNone(job['measurement']['official_pass'])
        self.assertIsNone(job['result'])
        self.assertFalse((self.root / 'results/development/latest-M07.json').exists())

    def assert_single_validation(self, job):
        self.assertIs(job['auto_validate'], True)
        self.assertEqual(job['validation_attempt_count'], 1)
        self.assertTrue(job['validation_started_at'])
        self.assertEqual(self.manager.launches, ['generate'])
        policy = job['trial_policy']['automatic_validation']
        self.assertIs(policy['enabled'], True)
        self.assertEqual(policy['max_attempts'], 1)
        self.assertEqual(policy['stages'], ['SYNTAX', 'EXECUTION_PREPARATION', 'EXECUTION'])
        self.assertEqual(policy['browser_not_ready'], 'PRESERVE_SYNTAX_NOT_READY')
        self.assertIs(policy['retry_on_unavailable_browser'], False)

    def test_one_create_fixes_twenty_originals_checks_once_and_saves_twenty_case_result(self):
        done = self.automatic()
        self.assertEqual(done['status'], 'COMPLETED', done.get('error'))
        self.assert_single_validation(done)
        self.assertEqual(len(self.calls), 20)
        self.assertEqual(self.manager.synthetic_runs, self.calls)
        self.assertEqual(done['counts']['syntax_pass_count'], 20)
        self.assertEqual(done['counts']['execution_pass_count'], 20)
        self.assertEqual(done['counts']['both_pass_count'], 20)
        self.assertEqual(done['measurement']['denominator'], 20)
        self.assertEqual(done['measurement']['integrated_percent'], 100)
        self.assertEqual(done['result']['sample_count'], 20)
        self.assertEqual(done['result']['score'], 100)
        self.assertIsNone(done['result']['official_pass'])
        self.assertNotIn('legacy_result', done)
        self.assertEqual(json.loads((self.root / 'results/development/latest-M07.json').read_bytes())['score'], 100)
        folder = self.folder(done)
        self.assertEqual(json.loads((folder / 'meeting_inputs.json').read_bytes()), self.original_payload)
        self.assertEqual(digest((folder / 'code.zip').read_bytes()), done['archive_sha256'])
        with zipfile.ZipFile(folder / 'code.zip') as archive:
            for case in done['cases']:
                expected = self.responses[case['scenario_id']]
                self.assertEqual(archive.read(case['case_id'] + '/script.py'), expected['code'])
                self.assertEqual(archive.read(case['case_id'] + '/response.json'), expected['response'])
                self.assertEqual(case['validation_code_sha256'], case['code_sha256'])
                self.assertEqual(digest(expected['code']), case['code_sha256'])

    def test_syntax_failure_and_static_preparation_refusal_are_not_browser_failures(self):
        first, second = [item['scenario']['scenario_id'] for item in self.payload['items'][:2]]
        self.code_factory = lambda source: ('def broken(:\n' if source['scenario_id'] == first else
                                           'SCENARIO_ID = ' + repr(second) + '\nassert True\n'
                                           if source['scenario_id'] == second else synthetic_code(source))
        done = self.automatic()
        self.assertEqual(done['status'], 'COMPLETED', done.get('error'))
        self.assert_single_validation(done)
        syntax, preparation = done['cases'][:2]
        self.assertEqual((syntax['syntax_status'], syntax['execution_status']), ('FAIL', 'SKIPPED'))
        self.assertEqual(syntax['execution_preparation_status'], 'SKIPPED')
        self.assertEqual(preparation['syntax_status'], 'PASS')
        self.assertEqual(preparation['execution_preparation_status'], 'FAIL')
        self.assertEqual(preparation['execution_status'], 'SKIPPED')
        self.assertNotIn(first, self.manager.synthetic_runs)
        self.assertNotIn(second, self.manager.synthetic_runs)
        self.assertEqual(len(self.manager.synthetic_runs), 18)
        self.assertEqual(done['counts']['syntax_pass_count'], 19)
        self.assertEqual(done['counts']['both_pass_count'], 18)
        self.assertEqual(done['result']['score'], 90)
        self.assertEqual(done['result']['sample_count'], 20)

    def test_four_execution_assertions_fail_without_reducing_fixed_denominator(self):
        self.manager.synthetic_failures = {item['scenario']['scenario_id'] for item in self.payload['items'][-4:]}
        done = self.automatic()
        self.assertEqual(len(self.calls), 20)
        self.assertEqual(len(self.manager.synthetic_runs), 20)
        self.assertEqual(done['counts']['syntax_pass_count'], 20)
        self.assertEqual(done['counts']['both_pass_count'], 16)
        self.assertEqual(done['result']['sample_count'], 20)
        self.assertEqual(done['result']['score'], 80)
        self.assertTrue(done['result']['threshold_met'])
        self.assertEqual([case['final_status'] for case in done['cases']][-4:], ['FAIL'] * 4)

    def test_first_429_stops_nineteen_unattempted_without_retry_or_zero_score(self):
        self.behavior[self.payload['items'][0]['scenario']['scenario_id']] = http_failure(429)
        done = self.automatic()
        self.assert_single_validation(done)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.manager.synthetic_runs, [])
        self.assertEqual(done['measurement']['provider_http_attempt_count'], 1)
        self.assertEqual(done['measurement']['not_attempted_count'], 19)
        self.assertEqual([c['generation_status'] for c in done['cases']], ['ERROR'] + ['SKIPPED'] * 19)
        self.assertTrue(done['provider_state']['blocked'])
        self.assert_not_ready(done)
        for case in done['cases'][1:]:
            self.assertIs(case['generation_http_attempted'], False)
            self.assertFalse((self.folder(done) / case['case_id'] / 'script.py').exists())
        with self.assertRaises(EvaluationError):
            self.manager.create_meeting(deepcopy(self.payload), auto_validate=True)
        self.assertEqual(len(self.calls), 1)

    def test_two_generated_then_429_checks_only_existing_originals_and_keeps_result_null(self):
        self.behavior[self.payload['items'][2]['scenario']['scenario_id']] = http_failure(429)
        done = self.automatic()
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len(self.manager.synthetic_runs), 2)
        self.assertEqual(done['counts']['syntax_pass_count'], 2)
        self.assertEqual(done['counts']['both_pass_count'], 2)
        self.assertEqual(done['measurement']['not_attempted_count'], 17)
        self.assert_not_ready(done)

    def test_absent_browser_preserves_all_python_syntax_and_never_scores_execution_zero(self):
        self.manager._readiness = lambda: dict(selenium=False, chrome=False, edge=False, message='SYNTHETIC no browser')
        done = self.automatic()
        self.assert_single_validation(done)
        self.assertEqual(done['status'], 'COMPLETED')
        self.assertEqual(len(self.calls), 20)
        self.assertEqual(self.manager.synthetic_runs, [])
        self.assertEqual(done['counts']['syntax_pass_count'], 20)
        for case in done['cases']:
            self.assertEqual(case['syntax_status'], 'PASS')
            self.assertEqual(case['execution_preparation_status'], 'NOT_READY')
            self.assertEqual(case['execution_status'], 'NOT_READY')
            self.assertNotEqual(case.get('browser_started'), True)
            self.assertEqual(case['validation_code_sha256'], case['code_sha256'])
        self.assert_not_ready(done)

    def test_busy_browser_lock_preserves_syntax_without_invoking_a_browser(self):
        lock_dir = self.root / 'data/development/m04_runner'
        lock_dir.mkdir(parents=True)
        lock = _RunLock(lock_dir / 'runner.lock')
        self.assertTrue(lock.acquire())
        try:
            done = self.automatic()
        finally:
            lock.close()
        self.assert_single_validation(done)
        self.assertEqual(done['counts']['syntax_pass_count'], 20)
        self.assertEqual(self.manager.synthetic_runs, [])
        self.assertTrue(all(case['execution_status'] == 'NOT_READY' for case in done['cases']))
        self.assert_not_ready(done)

    def test_default_and_explicit_false_keep_legacy_separate_inspection(self):
        for arguments in ({}, dict(auto_validate=False)):
            with self.subTest(arguments=arguments):
                generated = self.create(**arguments)
                self.assertEqual(generated['status'], 'GENERATED')
                self.assertFalse(generated.get('auto_validate', False))
                self.assertEqual(generated.get('validation_attempt_count', 0), 0)
                self.assertEqual(generated['counts']['syntax_pass_count'], 0)
                self.assertEqual(self.manager.synthetic_runs, [])
                self.assertIsNone(generated['result'])
        self.assertEqual(len(self.calls), 40)

    def test_automatic_job_cannot_validate_twice_or_allow_reentrant_generation(self):
        def cannot_create():
            with self.assertRaises(EvaluationError) as caught:
                self.manager.create_meeting(deepcopy(self.payload), auto_validate=True)
            self.assertEqual(caught.exception.status, 'RUNNING')
        self.provider_probe = cannot_create
        original_runner = self.manager._run_case
        probed = []
        def runner(job, case):
            if not probed:
                cannot_create()
                with self.assertRaises(EvaluationError):
                    self.manager.validate(job['generation_id'])
                probed.append(True)
            original_runner(job, case)
        with patch.object(self.manager, '_run_case', side_effect=runner):
            done = self.automatic()
        self.assertEqual(probed, [True])
        self.assert_single_validation(done)
        before = (len(self.calls), len(self.manager.synthetic_runs))
        with self.assertRaises(EvaluationError):
            self.manager.validate(done['generation_id'])
        self.assertEqual((len(self.calls), len(self.manager.synthetic_runs)), before)
        self.assertEqual(len(self.manager.list_runs()['generations']), 1)
        lock = self.manager._global_lock()
        self.assertIsNotNone(lock)
        lock.close()

    def test_auto_policy_hash_missing_or_changed_policy_rejects_before_provider(self):
        original_launch = self.manager._launch
        for mutation in ('MISSING_POLICY_HASH', 'CHANGED_POLICY_WITH_MATCHING_HASH'):
            with self.subTest(mutation=mutation):
                def tamper_before_launch(identity, phase, run_lock, browser_lock=None):
                    path = self.manager._job_path(identity)
                    stored = json.loads(path.read_bytes())
                    if mutation == 'MISSING_POLICY_HASH':
                        stored.pop('trial_policy_sha256')
                    else:
                        policy = deepcopy(stored['trial_policy'])
                        policy['automatic_validation']['enabled'] = False
                        raw = json.dumps(policy, ensure_ascii=False).encode('utf-8')
                        (path.parent / 'trial_policy.json').write_bytes(raw)
                        stored.update(trial_policy=policy, trial_policy_sha256=digest(raw))
                    path.write_text(json.dumps(stored, ensure_ascii=False), encoding='utf-8')
                    original_launch(identity, phase, run_lock, browser_lock)
                with patch.object(self.manager, '_launch', side_effect=tamper_before_launch):
                    done = self.automatic()
                self.assertEqual(done['status'], 'INTERRUPTED')
                self.assertEqual(done['automatic_phase'], 'INTERRUPTED')
                self.assertEqual(done['generation_stop']['reason'], 'FIXED_INPUT_INTEGRITY_ERROR')
                self.assertEqual(done['validation_attempt_count'], 0)
                self.assertEqual(done['measurement']['provider_http_attempt_count'], 0)
                self.assertEqual(self.calls, [])
                self.assertEqual(self.manager.synthetic_runs, [])
                self.assert_not_ready(done)
                self.assertEqual(json.loads((self.folder(done) / 'meeting_inputs.json').read_bytes()), self.original_payload)
                self.assertFalse(list(self.folder(done).glob('CASE-*/script.py')))

    def test_cancel_during_generation_stops_additional_calls_and_automatic_validation(self):
        self.provider_probe = lambda: self.manager.cancel(self.manager._active)
        with patch.object(self.manager, '_automatic_validate', wraps=self.manager._automatic_validate) as automatic:
            done = self.automatic()
        automatic.assert_not_called()
        self.assertEqual(done['status'], 'INTERRUPTED')
        self.assertEqual(done['automatic_phase'], 'INTERRUPTED')
        self.assertEqual(done['validation_attempt_count'], 0)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.manager.synthetic_runs, [])
        self.assertEqual(done['measurement']['provider_http_attempt_count'], 1)
        self.assertEqual(done['counts']['generated_code_count'], 1)
        self.assertEqual(done['counts']['syntax_pass_count'], 0)
        self.assertEqual([case['generation_status'] for case in done['cases']], ['PASS'] + ['SKIPPED'] * 19)
        self.assertTrue((self.folder(done) / 'cancel.request').is_file())
        self.assert_not_ready(done)
        self.manager.read(done['generation_id'])
        self.assertEqual(len(self.calls), 1)

    def test_recovery_interrupts_owned_pending_generated_auto_job_without_resuming(self):
        # A stopped worker may have fixed all originals but not entered its
        # opt-in inspection phase. Recreate the manager in the same owned scope.
        with patch.object(self.manager, '_automatic_validate', return_value=None):
            created = self.manager.create_meeting(self.payload, auto_validate=True)['generation']
            pending = self.manager._job(created['generation_id'])
        self.assertEqual(pending['status'], 'GENERATED')
        self.assertEqual(pending['validation_attempt_count'], 0)
        self.assertEqual(len(self.calls), 20)
        self.assertEqual(self.manager.synthetic_runs, [])
        folder = self.folder(pending)
        originals = {path.relative_to(folder).as_posix(): path.read_bytes() for path in
                     [folder / 'code.zip', folder / 'meeting_inputs.json', folder / 'trial_policy.json',
                      *folder.glob('CASE-*/script.py')]}
        with patch.object(SynchronousOneClickManager, '_launch', side_effect=AssertionError('No automatic resume')) as launch, \
                patch.object(SynchronousOneClickManager, '_run_case', side_effect=AssertionError('No resumed browser')) as run:
            recovered = SynchronousOneClickManager(self.root, lambda: deepcopy(self.config),
                                                   generator=self.provider, session=self.manager.session)
            done = recovered.read(pending['generation_id'])['generation']
            self.assertEqual(done['status'], 'INTERRUPTED')
            self.assertEqual(done['automatic_phase'], 'INTERRUPTED')
            self.assertEqual(done['validation_attempt_count'], 0)
            self.assert_not_ready(done)
            after_recovery = recovered._job_path(done['generation_id']).read_bytes()
            recovered._recover()
            self.assertEqual(recovered._job_path(done['generation_id']).read_bytes(), after_recovery)
            launch.assert_not_called()
            run.assert_not_called()
        self.assertEqual(len(self.calls), 20)
        self.assertEqual(self.manager.synthetic_runs, [])
        for name, raw in originals.items():
            self.assertEqual((folder / name).read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
