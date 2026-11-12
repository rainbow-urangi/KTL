"""Temporary synthetic CU02 evaluation fixtures. No real browser/site is used."""
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
from backend.m04 import cu02_evaluation
from backend.m04.store import M04Manager, _encoded, _screenshot_records
from backend.session import RuntimeSession


INPUT = dict(date='2028-02-29', title='SYNTHETIC CU02', description='Temporary synthetic business input', browser='edge')
STAMP = '2026-11-13T00:00:00+00:00'
LOGIN = dict(KTL_M04_RBEM_USERNAME='SYNTHETIC_TEST_ACCOUNT', KTL_M04_RBEM_PASSWORD='SYNTHETIC_TEST_PASSWORD')


class ImmediateThread:
    def __init__(self, *, target, args, **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class CU02EvaluationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='ktl-cu02-evaluation-synthetic-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.config = dict(targets={'M04': 90}, m04={}, m07={}, integration_datasets={})
        self.session = RuntimeSession()
        self.manager = M04Manager(self.root, lambda: self.config, session=self.session)
        self.enterContext(patch.dict(os.environ, LOGIN))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No synthetic test browser/subprocess')))
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No synthetic test network')))

    def prepare_without_worker(self, payload=None, observer=None):
        def no_execution(identity, lock):
            try:
                if observer:
                    observer(self.manager._job(identity))
            finally:
                lock.close()
        with patch.object(self.manager, '_execute', side_effect=no_execution), \
                patch('backend.m04.store.threading.Thread', ImmediateThread):
            return self.manager.create_cu02_evaluation(INPUT if payload is None else payload)

    def test_ten_distinct_cases_are_fixed_and_archived_before_worker_start(self):
        observed = []
        def before_worker(job):
            folder = self.manager.execution_directory / job['execution_id']
            raw = (folder / 'cu02_evaluation.json').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), job['cu02_evaluation_sha256'])
            with zipfile.ZipFile(self.root / 'data/evaluation' / job['dataset_id'] / 'scripts.zip') as archive:
                self.assertEqual(archive.read('cu02_evaluation.json'), raw)
                for row, case in zip(job['cu02_evaluation']['cases'], job['cases']):
                    self.assertEqual(json.loads(archive.read(case['case_id'] + '/cu02_parameters.json')), row['expected'])
                    self.assertEqual(archive.read(case['case_id'] + '/script.py'),
                                     (folder / case['case_id'] / 'script.py').read_bytes())
                    scenario = json.loads(archive.read(case['case_id'] + '/execution_scenario.json'))
                    self.assertEqual(scenario['screenshot_checkpoints'], {'before': 2, 'after': 5})
                    self.assertEqual(len(scenario['steps']), 5)
                inputs = json.loads(archive.read('fixed_scripts.json'))
                self.assertEqual(inputs['cu02_evaluation_sha256'], job['cu02_evaluation_sha256'])
            observed.append(job['execution_id'])
        response = self.prepare_without_worker(dict(INPUT, visible_browser=True, action_delay_ms=50, keep_open_seconds=1),
                                               before_worker)
        job, evaluation = response['execution'], response['evaluation']
        self.assertEqual(observed, [job['execution_id']])
        self.assertEqual(job['cu02_evaluation'], evaluation)
        self.assertEqual(evaluation['case_count'], 10)
        self.assertEqual(len(set(evaluation['script_ids'])), 10)
        self.assertEqual(len({row['expected']['title'] for row in evaluation['cases']}), 10)
        self.assertEqual(job['counts']['total_execution_count'], 10)
        self.assertIsNone(job['result'])
        self.assertTrue(job['visible_browser'])
        for number, case in enumerate(job['cases'], 1):
            self.assertEqual(case['cu02_case_number'], number)
            self.assertEqual(case['cu02_evaluation_id'], evaluation['evaluation_id'])
        encoded = json.dumps(response)
        for secret in LOGIN.values():
            self.assertNotIn(secret, encoded)

    def test_two_evaluations_have_separate_ids_inputs_and_case_snapshots(self):
        first = self.prepare_without_worker()
        second = self.prepare_without_worker()
        self.assertNotEqual(first['evaluation']['evaluation_id'], second['evaluation']['evaluation_id'])
        self.assertTrue(set(first['evaluation']['script_ids']).isdisjoint(second['evaluation']['script_ids']))
        self.assertTrue({row['expected']['title'] for row in first['evaluation']['cases']}.isdisjoint(
                        row['expected']['title'] for row in second['evaluation']['cases']))

    def test_invalid_inputs_and_missing_login_write_no_scripts_or_executions(self):
        variants = [None, [], {}, dict(INPUT, title='x' * 106), dict(INPUT, date='2027-02-29'),
                    dict(INPUT, script_ids=[]), dict(INPUT, case_count=9), dict(INPUT, run_mode='OFFICIAL'),
                    dict(INPUT, visible_browser='true'), dict(INPUT, action_delay_ms=1),
                    dict(INPUT, visible_browser=True, keep_open_seconds=True)]
        for payload in variants:
            with self.subTest(payload_type=type(payload).__name__), self.assertRaises(EvaluationError):
                self.manager.create_cu02_evaluation(payload)
        with patch.dict(os.environ, {key: '' for key in LOGIN}), self.assertRaises(EvaluationError):
            self.manager.create_cu02_evaluation(INPUT)
        self.assertEqual(list(self.manager.script_directory.iterdir()), [])
        self.assertEqual(list(self.manager.execution_directory.iterdir()), [])

    def test_running_browser_lock_refuses_new_evaluation_before_preparation(self):
        with patch.object(self.manager, '_global_lock', return_value=None), self.assertRaises(EvaluationError) as error:
            self.manager.create_cu02_evaluation(INPUT)
        self.assertEqual(error.exception.status, 'RUNNING')
        self.assertEqual(list(self.manager.script_directory.iterdir()), [])

    def test_evaluation_and_parameter_tampering_rejected_before_submission(self):
        response = self.prepare_without_worker()
        job = response['execution']
        original = deepcopy(job)
        job['cu02_evaluation']['cases'][0]['expected']['title'] = 'SYNTHETIC ALTERED'
        with self.assertRaises(EvaluationError):
            self.manager._provenance(job)
        job = deepcopy(original)
        folder = self.manager.execution_directory / job['execution_id']
        job['cu02_evaluation']['cases'][0]['expected']['title'] = 'SYNTHETIC ALTERED'
        raw = _encoded(job['cu02_evaluation'])
        (folder / 'cu02_evaluation.json').write_bytes(raw)
        job['cu02_evaluation_sha256'] = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(EvaluationError):
            self.manager._provenance(job)

    def test_nine_passes_and_one_technical_error_are_submitted_as_ninety_percent(self):
        # Exercise the real batch worker, provenance and central result calculation;
        # only the actual Selenium worker is replaced with synthetic outcomes.
        outcomes = []
        def synthetic_case(job, case):
            outcomes.append(case['case_id'])
            if case['cu02_case_number'] == 4:
                raise RuntimeError('SYNTHETIC BROWSER START ERROR')
            case.update(status='PASS', browser_started=True, completed_at=STAMP)
        with patch.object(self.manager, '_run_case', side_effect=synthetic_case), \
                patch('backend.m04.store.threading.Thread', ImmediateThread):
            response = self.manager.create_cu02_evaluation(INPUT)
        job = self.manager._job(response['execution']['execution_id'])
        self.assertEqual(job['status'], 'COMPLETED', job.get('error'))
        self.assertEqual(outcomes, [f'CASE-{number:03d}' for number in range(1, 11)])
        self.assertEqual(job['counts'], dict(total_execution_count=10, successful_execution_count=9, failed_execution_count=1))
        self.assertEqual(job['cases'][3]['status'], 'ERROR')
        self.assertEqual(job['result']['score'], 90)
        self.assertIsNone(job['result']['official_pass'])
        received = json.loads((self.root / 'results/development' / job['result']['run_id'] / 'received_payload.json').read_bytes())
        self.assertEqual(received['details']['cu02_evaluation'], job['cu02_evaluation'])
        self.assertEqual(received['counts']['total_execution_count'], 10)
        body, _ = self.manager.artifact(job['execution_id'], 'report.json')
        self.assertEqual(json.loads(body)['counts'], job['counts'])

    def test_target_is_ninety_percent_and_five_steps_never_become_five_cases(self):
        evaluation, prepared, _ = cu02_evaluation.build(dict(INPUT, title='x' * 105), STAMP)
        self.assertEqual(evaluation['required_success_count'], 9)
        self.assertEqual(evaluation['target_percent'], 90)
        self.assertEqual(evaluation['counting_unit'], 'SCHEDULE_REGISTRATION')
        self.assertEqual(len(prepared), 10)
        self.assertTrue(all(len(item['parameters']['title']) <= 120 for item in prepared))
        self.assertTrue(all(len(item['scenario']['steps']) == 5 for item in prepared))

    def test_checkpoint_metadata_is_preserved_and_invalid_positions_are_refused(self):
        record = dict(phase='before', file=None, sha256=None, policy='text-and-images-masked-v1', captured_at=STAMP,
                      status='NOT_CAPTURED', reason='checkpoint_not_reached',
                      capture_mode='EXPLICIT_BUSINESS_CHECKPOINT', business_step_order=2)
        self.assertEqual(_screenshot_records([record]), [record])
        for number in (True, 0, -1, 1001, '2'):
            with self.subTest(position=number), self.assertRaises(EvaluationError):
                _screenshot_records([dict(record, business_step_order=number)])


if __name__ == '__main__':
    unittest.main()
