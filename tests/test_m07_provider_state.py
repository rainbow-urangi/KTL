"""Temporary synthetic manager/transport evidence; no provider or browser calls."""
import copy
import base64
import hashlib
from datetime import datetime, timedelta, timezone
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from backend.evaluators import EvaluationError
from backend.m07 import generator
from backend.m07.store import M07Manager


RUN = 'DEV-M03-20261111T010000-abcdef123456'
MODEL = 'synthetic-model'


class SynchronousManager(M07Manager):
    def _launch(self, identity, phase, run_lock, browser_lock=None):
        try:
            job = self._job(identity)
            self._generate(job) if phase == 'generate' else self._validate(job)
        finally:
            if browser_lock:
                browser_lock.close()
            run_lock.close()

    def _run_case(self, job, case):
        case.update(status='PASS', started_at='2026-11-11T01:00:00+00:00', worker_pid=123,
                    browser_started=True, business_step_complete=True, independent_checks_passed=True)


class ProviderStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ktl-m07-cooldown-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = dict(m07=dict(model=MODEL, target_url='https://example.invalid/synthetic'), targets=dict(M07=80))
        self.calls = []
        self.behavior = {}
        folder = self.root / 'results/development' / RUN
        folder.mkdir(parents=True)
        self.sources = [dict(scenario_id='SYNTHETIC-' + str(i), business_unit_id='BU-' + str(i),
            workflow_id='WF-' + str(i), scenario_name='Synthetic', status='SUCCESS',
            steps=[dict(order=1, action='open', target='Synthetic page', expected_result='Synthetic outcome')],
            execution_contract=dict(version=1, scenario_id='SYNTHETIC-' + str(i), steps=[dict(order=1, action='open',
                target=dict(url='https://example.invalid/synthetic'), checks=[dict(kind='url_path', expected='/synthetic')])])) for i in range(1, 21)]
        (folder / 'result.json').write_text(json.dumps(dict(metric_id='M03', run_mode='DEVELOPMENT', status='COMPLETED')), encoding='utf-8')
        (folder / 'received_payload.json').write_text(json.dumps(dict(scenarios=self.sources)), encoding='utf-8')
        self.manager = self.manager_for(self.provider)

    def manager_for(self, callback):
        manager = SynchronousManager(self.root, lambda: copy.deepcopy(self.config), generator=callback)
        manager._readiness = lambda: dict(selenium=True, chrome=True, message='SYNTHETIC_ONLY')
        return manager

    def provider(self, root, config, scenario):
        identity = scenario['scenario_id']
        self.calls.append(identity)
        value = self.behavior.get(identity)
        if isinstance(value, Exception):
            raise value
        code = ('from selenium import webdriver\nSCENARIO_ID = ' + repr(identity) + '\nassert True\n')
        return dict(code=code, response=dict(id='req_synthetic', output=code),
                    response_bytes=json.dumps(dict(output=code)).encode('utf-8'),
                    requested_model=MODEL, model=MODEL, request_id='req_synthetic', generated_by_llm=True,
                    http_request_attempted=True, provider_response_observed=True)

    @staticmethod
    def rate_error(retry=50881):
        return generator.GenerationError('Synthetic HTTP429', dict(model=MODEL, requested_model=MODEL,
            http_request_attempted=True, provider_response_observed=True,
            response=dict(http_status=429, body_policy='HASH_ONLY', diagnostics=dict(
                error_type='tokens', error_code='rate_limit_exceeded', numeric_headers={'retry-after': retry}))))

    def create(self, count=3, manager=None):
        manager = manager or self.manager
        job = manager.create(dict(m03_run_id=RUN, scenario_ids=['SYNTHETIC-' + str(i) for i in range(1, count + 1)]))['generation']
        return manager.read(job['generation_id'])['generation']

    def validate(self, job, manager=None):
        manager = manager or self.manager
        manager.validate(job['generation_id'])
        return manager.read(job['generation_id'])['generation']

    def test_first_429_stops_without_sleep_or_more_generator_calls(self):
        self.behavior['SYNTHETIC-1'] = self.rate_error()
        with mock.patch('backend.m07.store.ingest') as ingest:
            job = self.create(20)
            done = self.validate(job)
        self.assertEqual(self.calls, ['SYNTHETIC-1'])
        self.assertEqual([c['generation_status'] for c in done['cases']], ['ERROR'] + ['SKIPPED'] * 19)
        self.assertEqual((done['measurement']['provider_http_attempt_count'], done['measurement']['not_attempted_count']), (1, 19))
        self.assertEqual(done['measurement']['evaluation_status'], 'NOT_READY')
        self.assertIsNone(done['result'])
        self.assertIsNone(done['measurement']['syntax_percent'])
        self.assertEqual(done['provider_state']['retry_after_seconds'], 50881)
        ingest.assert_not_called()

    def test_two_successes_then_429_partial_never_ingests_or_scores_100(self):
        self.behavior['SYNTHETIC-3'] = self.rate_error()
        with mock.patch.object(self.manager, '_evaluate') as evaluate, mock.patch('backend.m07.store.ingest') as ingest:
            done = self.validate(self.create(10))
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(done['measurement']['registered_count'], 10)
        self.assertEqual(done['measurement']['generated_code_count'], 2)
        self.assertEqual(done['measurement']['both_pass_count'], 2)
        self.assertEqual(done['measurement']['not_attempted_count'], 7)
        for key in ('generation_percent', 'syntax_percent', 'integrated_percent', 'browser_percent', 'syntax_target_met', 'integrated_reference_target_met'):
            self.assertIsNone(done['measurement'][key])
        evaluate.assert_not_called()
        ingest.assert_not_called()
        self.assertIsNone(done['result'])
        self.assertFalse((self.root / 'results/development/latest-M07.json').exists())

    def test_cooldown_persists_restart_and_gate_does_not_call_generator(self):
        self.behavior['SYNTHETIC-1'] = self.rate_error()
        job = self.create()
        restarted = self.manager_for(self.provider)
        with self.assertRaises(EvaluationError):
            self.create(manager=restarted)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(restarted.list_runs()['generations']), 1)
        self.assertTrue(restarted.read(job['generation_id'])['provider_state']['blocked'])

    def test_expiry_requires_explicit_new_create_and_decorates_without_rewriting(self):
        self.behavior['SYNTHETIC-1'] = self.rate_error(60)
        job = self.create()
        path = self.manager._job_path(job['generation_id'])
        old = path.read_bytes()
        after = datetime.fromisoformat(job['provider_state']['next_eligible_at']) + timedelta(seconds=1)
        self.manager.provider_state.clock = lambda: after
        self.assertFalse(self.manager.read(job['generation_id'])['provider_state']['blocked'])
        self.assertEqual(old, path.read_bytes())
        self.assertEqual(len(self.calls), 1)
        self.behavior.clear()
        self.create(1)
        self.assertEqual(len(self.calls), 2)

    def test_pre_http_failure_is_zero_attempt_not_unknown(self):
        self.behavior['SYNTHETIC-1'] = generator.GenerationError('Synthetic preflight failure', dict(
            http_request_attempted=False, provider_response_observed=False, response={}))
        with mock.patch.object(self.manager, '_evaluate') as evaluate:
            done = self.validate(self.create(1))
        self.assertEqual(done['measurement']['provider_http_attempt_count'], 0)
        self.assertEqual(done['measurement']['provider_http_unknown_count'], 0)
        self.assertEqual(done['measurement']['not_attempted_count'], 1)
        self.assertIsNone(done['result'])
        evaluate.assert_not_called()

    def test_flagless_generator_unknown_never_infers_actual_http_from_request_id(self):
        def unknown(*args):
            value = self.provider(*args)
            value.pop('http_request_attempted')
            value.pop('provider_response_observed')
            return value
        manager = self.manager_for(unknown)
        with mock.patch.object(manager, '_evaluate') as evaluate:
            done = self.validate(self.create(1, manager), manager)
        self.assertEqual(done['measurement']['provider_http_attempt_count'], 0)
        self.assertEqual(done['measurement']['provider_http_unknown_count'], 1)
        self.assertEqual(done['measurement']['provider_http_inferred_count'], 1)
        self.assertEqual(done['measurement']['evaluation_status'], 'NOT_READY')
        evaluate.assert_not_called()

    def test_plain_exception_is_unknown_and_partial_no_result(self):
        self.behavior['SYNTHETIC-1'] = EvaluationError('Synthetic callback failure')
        done = self.validate(self.create(1))
        self.assertEqual(done['measurement']['provider_http_unknown_count'], 1)
        self.assertEqual(done['measurement']['evaluation_status'], 'NOT_READY')
        self.assertIsNone(done['result'])

    def test_http_transport_failure_attempted_distinct_from_response_observed(self):
        self.behavior['SYNTHETIC-1'] = generator.GenerationError('Synthetic transport failure', dict(
            http_request_attempted=True, provider_response_observed=False, response={}))
        done = self.validate(self.create(1))
        self.assertEqual(done['measurement']['provider_http_attempt_count'], 1)
        self.assertEqual(done['measurement']['provider_response_count'], 0)
        self.assertEqual(done['measurement']['evaluation_status'], 'COMPLETED')
        self.assertEqual(done['measurement']['generation_percent'], 0)
        self.assertIsNone(done['result'])

    def test_registered_20_syntax_80_integrated_50_are_separate(self):
        cases = []
        for i in range(20):
            cases.append(dict(generation_status='PASS' if i < 16 else 'ERROR',
                syntax_status='PASS' if i < 16 else 'SKIPPED', execution_status='PASS' if i < 10 else 'FAIL' if i < 15 else 'SKIPPED',
                generation_invoked=True, generation_http_attempted=True, provider_response_observed=True,
                browser_started=i < 15, started_at='synthetic' if i < 15 else None))
        job = dict(status='COMPLETED', cases=cases, measurement_version=1)
        self.manager._counts(job)
        self.manager._measurement(job)
        measurement = job['measurement']
        self.assertEqual((measurement['generation_percent'], measurement['syntax_percent'], measurement['integrated_percent']), (80, 80, 50))
        self.assertAlmostEqual(measurement['browser_percent'], 100 * 10 / 15)
        self.assertTrue(measurement['syntax_target_met'])
        self.assertFalse(measurement['integrated_reference_target_met'])
        self.assertIsNone(measurement['official_pass'])

    def test_historical_result_preserved_and_no_measurement_backfill(self):
        job = self.create(1)
        path = self.manager._job_path(job['generation_id'])
        legacy = json.loads(path.read_bytes())
        legacy.pop('measurement_version')
        legacy.pop('measurement')
        legacy.update(status='COMPLETED', result=dict(score=100, sample_count=1))
        path.write_text(json.dumps(legacy), encoding='utf-8')
        before = path.read_bytes()
        actual = self.manager.read(job['generation_id'])['generation']
        self.assertEqual(actual['result'], legacy['result'])
        self.assertNotIn('measurement', actual)
        self.assertEqual(path.read_bytes(), before)

    def test_corrupt_state_fails_closed_and_no_generator_call(self):
        self.manager.provider_state.path.write_text('{"version":1,"models":[]}', encoding='utf-8')
        with self.assertRaises(EvaluationError):
            self.create()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.manager._provider_current()['reason'], 'PROVIDER_STATE_INVALID')

    def test_trusted_seed_validates_timestamp_allowlists_and_excludes_raw_values(self):
        old = datetime(2026, 11, 11, tzinfo=timezone.utc)
        value = dict(http_status=429, diagnostics=dict(error_type=['unsafe'], error_code={'unsafe': 1},
                     message='SYNTHETIC_SECRET_NOT_TO_STORE', numeric_headers={'retry-after': 50881}))
        state = self.manager.provider_state.record(MODEL, value, observed_at=old)
        raw = self.manager.provider_state.path.read_text(encoding='utf-8')
        self.assertNotIn('SYNTHETIC_SECRET_NOT_TO_STORE', raw)
        self.assertIsNone(state['error_type'])
        self.assertEqual(datetime.fromisoformat(state['next_eligible_at']), old + timedelta(seconds=50881))

    def test_unsafe_retry_values_use_bounded_fallback(self):
        for value in (True, float('nan'), float('inf'), -1, 86401, '50881'):
            with self.subTest(value=str(value)):
                state = self.manager.provider_state.record(MODEL, self.rate_error(value).evidence['response'])
                self.assertEqual(state['retry_after_seconds'], 60)

    def test_provider_state_storage_failure_stops_remaining(self):
        self.behavior['SYNTHETIC-1'] = self.rate_error()
        with mock.patch.object(self.manager.provider_state, 'write', side_effect=OSError('Synthetic write failure')):
            job = self.create()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(job['provider_state']['reason'], 'PROVIDER_STATE_INVALID')
        with self.assertRaises(EvaluationError):
            self.create()

    def test_real_generator_mock_http_429_flags_reach_manager(self):
        def callback(root, config, scenario):
            return generator.generate(root, config, scenario)
        manager = self.manager_for(callback)
        failure = urllib.error.HTTPError('https://api.openai.com/v1/responses', 429, 'Synthetic',
            {'retry-after': '13505'}, io.BytesIO(b'{"error":{"type":"tokens","code":"rate_limit_exceeded"}}'))
        synthetic_settings = dict(model=MODEL, target_url='https://example.invalid/synthetic', api_key='SYNTHETIC_NOT_A_REAL_KEY')
        with mock.patch.object(generator, 'settings', return_value=synthetic_settings), \
                mock.patch.object(generator.urllib.request, 'urlopen', side_effect=failure) as transport:
            job = self.create(10, manager)
        transport.assert_called_once()
        self.assertEqual(job['measurement']['provider_http_attempt_count'], 1)
        self.assertEqual(job['measurement']['provider_response_count'], 1)
        self.assertEqual(job['measurement']['not_attempted_count'], 9)
        self.assertEqual(job['provider_state']['retry_after_seconds'], 13505)

    def test_cancel_check_between_calls_preserves_unattempted_and_no_result(self):
        original = self.provider
        def cancel_after_first(*args):
            value = original(*args)
            identity = next(self.manager.execution_directory.glob('*/execution.json')).parent.name
            (self.manager.execution_directory / identity / 'cancel.request').touch()
            return value
        self.manager.generator = cancel_after_first
        job = self.create()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(job['status'], 'INTERRUPTED')
        self.assertEqual(job['measurement']['not_attempted_count'], 2)
        self.assertIsNone(job['result'])

    def test_failed_browser_start_does_not_count_worker_or_start_timestamp(self):
        job = dict(status='COMPLETED', measurement_version=1, cases=[dict(generation_status='PASS',
            syntax_status='PASS', execution_status='ERROR', generation_invoked=True, generation_http_attempted=True,
            browser_started=False, started_at='synthetic', worker_pid=123)])
        self.manager._counts(job)
        self.manager._measurement(job)
        self.assertEqual(job['measurement']['browser_started_count'], 0)
        self.assertIsNone(job['measurement']['browser_percent'])
        self.assertEqual(job['measurement']['integrated_percent'], 0)

    def test_full_confirmed_job_keeps_legacy_result_explicitly_separate(self):
        done = self.validate(self.create(1))
        self.assertEqual(done['measurement']['evaluation_status'], 'COMPLETED')
        self.assertEqual(done['measurement']['integrated_percent'], 100)
        self.assertEqual(done['result_scope'], 'LEGACY_GENERATED_CODE_COUNT')
        self.assertEqual(done['legacy_result'], done['result'])
        self.assertIsNone(done['result']['official_pass'])

    def test_prepared_path_ignores_provider_cooldown_and_has_no_llm_measurement(self):
        self.manager.provider_state.record(MODEL, self.rate_error().evidence['response'])
        raw = self.provider(self.root, self.config, self.sources[0])['code'].encode('utf-8')
        self.calls.clear()
        value = self.manager.create(dict(m03_run_id=RUN, scenario_ids=['SYNTHETIC-1'], prepared_codes=[dict(
            scenario_id='SYNTHETIC-1', filename='synthetic.py', code_base64=base64.b64encode(raw).decode('ascii'),
            sha256=hashlib.sha256(raw).hexdigest())]))['generation']
        done = self.validate(self.manager.read(value['generation_id'])['generation'])
        self.assertEqual(self.calls, [])
        self.assertNotIn('measurement', done)
        self.assertEqual(done['result']['details']['code_source'], 'PREPARED')
        self.assertEqual(done['result']['score'], 100)

    def test_provider_state_is_model_scoped_and_current_context_is_effective(self):
        self.manager.provider_state.record(MODEL, self.rate_error().evidence['response'])
        self.assertTrue(self.manager.current_provider_state()['blocked'])
        self.config['m07']['model'] = 'another-synthetic-model'
        self.assertFalse(self.manager.current_provider_state()['blocked'])
        self.assertFalse(self.manager.context()['provider_state']['blocked'])

    def test_not_attempted_cases_have_no_fabricated_prompt_or_response_files(self):
        self.behavior['SYNTHETIC-1'] = self.rate_error()
        job = self.create()
        for case in job['cases'][1:]:
            folder = self.manager._job_path(job['generation_id']).parent / case['case_id']
            self.assertTrue((folder / 'source_scenario.json').is_file())
            self.assertFalse((folder / 'response.json').exists())
            self.assertFalse((folder / 'prompt.json').exists())
            self.assertNotIn('generation_started_at', case)

    def test_http_429_with_zero_retry_still_stops_same_job(self):
        self.behavior['SYNTHETIC-1'] = self.rate_error(0)
        job = self.create()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(job['provider_state']['blocked'])
        self.assertEqual(job['measurement']['not_attempted_count'], 2)
        self.assertIsNone(job['measurement']['generation_percent'])

    def test_new_or_older_seed_never_shortens_existing_later_cooldown(self):
        observed = datetime.now(timezone.utc)
        first = self.manager.provider_state.record(MODEL, self.rate_error(100).evidence['response'], observed_at=observed)
        path = self.manager.provider_state.path
        before = path.read_bytes()
        for offset in (1, -100):
            with self.subTest(offset=offset):
                later = self.manager.provider_state.record(MODEL, self.rate_error(10).evidence['response'],
                    observed_at=observed + timedelta(seconds=offset))
                self.assertEqual(later['next_eligible_at'], first['next_eligible_at'])
                self.assertEqual(path.read_bytes(), before)
        extended = self.manager.provider_state.record(MODEL, self.rate_error(200).evidence['response'], observed_at=observed)
        self.assertEqual(datetime.fromisoformat(extended['next_eligible_at']), observed + timedelta(seconds=200))

    def test_capacity_rejected_before_write_preserves_all_128_previous_models(self):
        observed = datetime.now(timezone.utc)
        for index in range(128):
            self.manager.provider_state.record('synthetic-' + str(index), self.rate_error().evidence['response'], observed_at=observed)
        path = self.manager.provider_state.path
        before = path.read_bytes()
        with self.assertRaises(EvaluationError):
            self.manager.provider_state.record('synthetic-129', self.rate_error().evidence['response'], observed_at=observed)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(json.loads(before)['models']), 128)
        restarted = self.manager_for(self.provider)
        self.assertEqual(restarted.provider_state.current('synthetic-0')['reason'], 'HTTP_429_COOLDOWN')


if __name__ == '__main__':
    unittest.main()
