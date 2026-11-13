"""Trial provenance and denominator regressions; all providers/browsers are synthetic."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import zipfile

from backend.evaluators import EvaluationError
from backend.m07 import generator
from backend.m07.store import M07Manager
from tests import test_m07_meeting_runner as support


class TrialExecutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = support.MeetingRunnerTests(
            'test_twenty_frozen_inputs_generate_twenty_originals_before_separate_inspection')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_all_generation_plans_are_fixed_before_the_first_provider_call(self):
        fixture = self.fixture
        observed = []
        original = fixture.manager.generator

        def inspect(root, config, scenario):
            job = fixture.manager._job(fixture.manager._active)
            folder = fixture.folder(job)
            policy = json.loads((folder / 'trial_policy.json').read_bytes())
            self.assertEqual(policy, job['trial_policy'])
            self.assertEqual(policy['input_count'], 20)
            self.assertEqual(len(list(folder.glob('CASE-*/generation_plan.json'))), 20)
            for case in job['cases']:
                raw = (folder / case['case_id'] / 'generation_plan.json').read_bytes()
                self.assertEqual(support.digest(raw), case['generation_plan_sha256'])
            observed.append(scenario['scenario_id'])
            return original(root, config, scenario)

        fixture.manager.generator = inspect
        job = fixture.create()
        self.assertEqual(len(observed), 20)
        self.assertEqual(job['measurement']['evaluation_status'], 'NOT_READY')
        self.assertIsNone(job['measurement']['syntax_percent'])
        with zipfile.ZipFile(fixture.folder(job) / 'code.zip') as archive:
            self.assertEqual(json.loads(archive.read('trial_policy.json')), job['trial_policy'])
            self.assertEqual(len([p for p in archive.namelist() if p.endswith('/generation_plan.json')]), 20)

    def test_ten_businesses_in_two_explicit_batches_are_twenty_actual_inputs(self):
        fixture = self.fixture
        originals = deepcopy(fixture.expected_input['items'][:10])
        rows, batches = [], []
        for batch in ('FIRST', 'SECOND'):
            group = []
            for number, original in enumerate(originals, 1):
                row = deepcopy(original)
                row['input_id'] = f'{batch}-{number:02d}'
                rows.append(row)
                group.append(row['input_id'])
            batches.append(dict(batch_id=batch, input_ids=group))
        fixture.expected_input = dict(items=rows, trial_policy=dict(batches=batches))
        generated = fixture.create()
        policy = generated['trial_policy']
        self.assertEqual((policy['input_count'], policy['business_unit_count'], policy['batch_count']), (20, 10, 2))
        self.assertEqual(policy['distinct_scenario_count'], 10)
        self.assertEqual([c['batch_id'] for c in generated['cases']], ['FIRST'] * 10 + ['SECOND'] * 10)
        done = fixture.validate(generated)
        self.assertEqual(len(fixture.calls), 20)
        self.assertEqual(done['measurement']['integrated_percent'], 100)
        self.assertIsNone(done['result']['official_pass'])
        self.assertEqual(done['result']['details']['trial_policy'], policy)

    def test_model_change_after_registration_stops_before_any_http_request(self):
        fixture = self.fixture
        changed = [False]
        fixture.manager.generator = generator.generate
        fixture.enterContext(patch.object(generator, 'settings', side_effect=lambda *args: dict(
            api_key='SYNTHETIC-NOT-FOR-NETWORK', model='SYNTHETIC-CHANGED' if changed[0] else support.MODEL,
            target_url='https://synthetic.example.invalid/login')))
        original_launch = fixture.manager._launch

        def launch(*args, **kwargs):
            changed[0] = True
            return original_launch(*args, **kwargs)

        fixture.manager._launch = launch
        with patch.object(generator.urllib.request, 'urlopen', side_effect=AssertionError('No network')) as network:
            generated = fixture.create()
        network.assert_not_called()
        self.assertEqual(generated['generation_stop']['reason'], 'GENERATION_SPEC_CHANGED')
        self.assertEqual(generated['cases'][0]['generation_status'], 'ERROR')
        self.assertEqual([c['generation_status'] for c in generated['cases'][1:]], ['SKIPPED'] * 19)
        self.assertEqual(generated['measurement']['provider_http_attempt_count'], 0)
        self.assertEqual(generated['measurement']['not_attempted_count'], 20)
        done = fixture.validate(generated)
        self.assertEqual(done['measurement']['evaluation_status'], 'NOT_READY')
        self.assertIsNone(done['measurement']['integrated_percent'])
        self.assertIsNone(done['result'])

    def test_syntax_valid_code_with_wrong_scenario_is_a_terminal_preparation_failure(self):
        fixture = self.fixture
        original = fixture.code_factory
        first = fixture.expected_input['items'][0]['scenario']['scenario_id']
        fixture.code_factory = lambda scenario: original(scenario).replace(repr(first), repr('WRONG-SCENARIO'))
        done = fixture.validate(fixture.create())
        rejected = done['cases'][0]
        self.assertEqual(rejected['syntax_status'], 'PASS')
        self.assertEqual(rejected['execution_preparation_status'], 'FAIL')
        self.assertEqual(rejected['execution_status'], 'SKIPPED')
        self.assertFalse(rejected.get('browser_started', False))
        self.assertEqual(done['measurement']['registered_count'], 20)
        self.assertEqual(done['measurement']['syntax_percent'], 100)
        self.assertEqual(done['measurement']['integrated_percent'], 95)
        self.assertEqual(done['measurement']['browser_started_count'], 19)
        self.assertEqual(done['measurement']['browser_percent'], 100)

    def test_generation_plan_tampering_cannot_be_used_for_inspection(self):
        fixture = self.fixture
        job = fixture.create()
        case = job['cases'][0]
        path = fixture.folder(job) / case['case_id'] / 'generation_plan.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaises(EvaluationError):
            fixture.manager.code(job['generation_id'], case['case_id'])
        self.assertEqual(fixture.manager.synthetic_runs, [])

    def test_a_corrupt_later_plan_stops_before_the_first_provider_call(self):
        fixture = self.fixture
        original_launch = fixture.manager._launch

        def launch(identity, *args, **kwargs):
            folder = fixture.manager.execution_directory / identity
            path = folder / 'CASE-020' / 'generation_plan.json'
            path.write_bytes(path.read_bytes() + b' ')
            return original_launch(identity, *args, **kwargs)

        fixture.manager._launch = launch
        created = fixture.manager.create_meeting(deepcopy(fixture.expected_input))['generation']
        job = fixture.manager.read(created['generation_id'])['generation']
        self.assertEqual(job['status'], 'INTERRUPTED')
        self.assertEqual(job['generation_stop']['reason'], 'FIXED_INPUT_INTEGRITY_ERROR')
        self.assertEqual(fixture.calls, [])
        self.assertEqual(job['measurement']['not_attempted_count'], 20)
        self.assertEqual(job['measurement']['evaluation_status'], 'NOT_READY')
        self.assertTrue(all(c['execution_preparation_status'] == 'SKIPPED' for c in job['cases']))
        self.assertIsNone(job['result'])


class RegisteredDenominatorTests(unittest.TestCase):
    def job(self):
        cases = []
        for number in range(20):
            generated, executed = number < 16, number < 10
            cases.append(dict(generation_status='PASS' if generated else 'ERROR',
                              syntax_status='PASS' if generated else 'SKIPPED',
                              execution_status='PASS' if executed else 'FAIL' if number < 15 else 'SKIPPED',
                              generation_invoked=True, generation_http_attempted=True,
                              provider_response_observed=True, browser_started=number < 15))
        job = dict(status='COMPLETED', measurement_version=1, meeting_protocol=True, cases=cases)
        M07Manager._counts(job)
        return job

    def test_registered_syntax_integrated_and_browser_denominators_are_distinct(self):
        job = self.job()
        M07Manager._measurement(job)
        value = job['measurement']
        self.assertEqual(value['evaluation_status'], 'COMPLETED')
        self.assertEqual(value['syntax_percent'], 80)
        self.assertEqual(value['integrated_percent'], 50)
        self.assertAlmostEqual(value['browser_percent'], 1000 / 15)
        self.assertEqual(value['denominator'], 20)
        self.assertEqual(value['browser_started_count'], 15)
        self.assertEqual(value['official_formula'], 'both_pass_count / 20 * 100')
        self.assertEqual(value['legacy_formula'], 'both_pass_count / generated_code_count * 100')

    def test_missing_attempt_unknown_attempt_or_nonterminal_check_prevents_all_final_rates(self):
        for change in ('unattempted', 'unknown', 'unfinished'):
            job = self.job()
            last = job['cases'][-1]
            if change == 'unattempted':
                last['generation_http_attempted'] = False
            elif change == 'unknown':
                last['generation_http_attempted'] = None
            else:
                last['execution_status'] = 'PENDING'
            M07Manager._measurement(job)
            self.assertEqual(job['measurement']['evaluation_status'], 'NOT_READY', change)
            for key in ('generation_percent', 'syntax_percent', 'integrated_percent', 'browser_percent'):
                self.assertIsNone(job['measurement'][key], (change, key))
