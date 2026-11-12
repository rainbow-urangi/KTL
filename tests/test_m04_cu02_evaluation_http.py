"""Loopback HTTP integration using temporary synthetic inputs and no browser worker."""
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.m04.store import M04Manager
from backend.server import LocalHTTPServer, Service, make_handler


INPUT = dict(date='2028-02-29', title='SYNTHETIC HTTP CU02',
             description='Temporary synthetic HTTP evaluation input', browser='edge')
LOGIN = dict(KTL_M04_RBEM_USERNAME='SYNTHETIC_HTTP_ACCOUNT',
             KTL_M04_RBEM_PASSWORD='SYNTHETIC_HTTP_PASSWORD')
PATH = '/api/development/m04/cu02/evaluations'


class CU02EvaluationHTTPTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='ktl-cu02-http-synthetic-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.config = dict(targets={'M04': 90}, m04={}, m07={}, integration_datasets={})
        self.service = Service(self.root, session_scoped=True)
        self.service.config = lambda: self.config
        # Freeze source state for this isolated test; another developer may edit
        # source files while the test runs. The rejection test changes this flag.
        self.service.runtime_build.status = lambda: dict(source_current=True)
        self.manager = M04Manager(self.root, self.service.config, session=self.service.session)
        self.service._m04 = self.manager
        self.outcomes = []
        self.enterContext(patch.dict(os.environ, LOGIN))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No test subprocess/browser')))
        self.enterContext(patch.object(self.manager, '_run_case', side_effect=self.synthetic_case))
        handler = make_handler(self.service)
        handler.log_message = lambda *args: None
        self.server = LocalHTTPServer(('127.0.0.1', 0), handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)
        self.assertFalse(self.worker.is_alive())

    def synthetic_case(self, job, case):
        self.outcomes.append(case['case_id'])
        if case['cu02_case_number'] == 4:
            raise RuntimeError('SYNTHETIC HTTP BROWSER START ERROR')
        case.update(status='PASS', browser_started=True, completed_at='2026-11-13T00:00:00+00:00')

    def request(self, method, path, payload=None, headers=None):
        request_headers = {'Content-Type': 'application/json'}
        request_headers.update(headers or {})
        body = json.dumps(payload).encode('utf-8') if payload is not None else None
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read()), dict(response.getheaders())
        finally:
            connection.close()

    def assert_no_prepared_or_executed_work(self):
        self.assertEqual(list(self.manager.script_directory.iterdir()), [])
        self.assertEqual(list(self.manager.execution_directory.iterdir()), [])
        self.assertEqual(self.outcomes, [])

    def test_post_fixes_ten_cases_and_poll_reads_real_ninety_percent_aggregation(self):
        origin = 'http://127.0.0.1:' + str(self.server.server_port)
        status, body, headers = self.request('POST', PATH, INPUT, {'Origin': origin})
        self.assertEqual(status, 201, body)
        self.assertEqual(headers['X-KTL-Server-Session'], self.service.session.id)
        evaluation, execution = body['evaluation'], body['execution']
        self.assertEqual(evaluation['workflow_id'], 'CU02')
        self.assertEqual(evaluation['counting_unit'], 'SCHEDULE_REGISTRATION')
        self.assertEqual(evaluation['case_count'], 10)
        self.assertEqual(evaluation['required_success_count'], 9)
        self.assertEqual(len(set(evaluation['script_ids'])), 10)
        self.assertEqual(execution['cu02_evaluation'], evaluation)
        self.assertEqual(execution['counts']['total_execution_count'], 10)
        self.assertEqual(len(execution['cases']), 10)
        read_path = '/api/development/m04/executions/' + execution['execution_id']
        deadline = time.monotonic() + 10
        while True:
            status, polled, _ = self.request('GET', read_path)
            self.assertEqual(status, 200, polled)
            job = polled['execution']
            if job['status'] not in {'QUEUED', 'RUNNING'} or time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        self.assertEqual(job['status'], 'COMPLETED', job.get('error'))
        self.assertEqual(self.outcomes, [f'CASE-{number:03d}' for number in range(1, 11)])
        self.assertEqual(job['counts'], dict(total_execution_count=10, successful_execution_count=9,
                                             failed_execution_count=1))
        self.assertEqual(job['cases'][3]['status'], 'ERROR')
        self.assertEqual(job['result']['score'], 90)
        self.assertIsNone(job['result']['official_pass'])
        self.assertEqual(job['cu02_evaluation'], evaluation)
        status, report, _ = self.request('GET', read_path + '/artifacts/report.json')
        self.assertEqual(status, 200, report)
        self.assertEqual(report['counts'], job['counts'])
        serialized = json.dumps(body) + json.dumps(polled) + json.dumps(report)
        self.assertTrue(all(secret not in serialized for secret in LOGIN.values()))

    def test_cross_origin_and_untrusted_host_are_refused_before_preparation(self):
        for headers in ({'Origin': 'https://foreign.invalid'}, {'Host': 'foreign.invalid:12345'}):
            with self.subTest(headers=headers):
                status, body, _ = self.request('POST', PATH, INPUT, headers)
                self.assertEqual(status, 403, body)
                self.assert_no_prepared_or_executed_work()

    def test_stale_sources_refuse_new_evaluation_but_keep_read_routes_available(self):
        self.service.runtime_build.status = lambda: dict(source_current=False)
        status, body, _ = self.request('POST', PATH, INPUT)
        self.assertEqual(status, 409, body)
        self.assertEqual(body['status'], 'RESTART_REQUIRED')
        self.assert_no_prepared_or_executed_work()
        status, body, _ = self.request('GET', '/api/development/m04/executions')
        self.assertEqual(status, 200, body)
        self.assertEqual(body['executions'], [])

    def test_official_mode_and_caller_selected_denominator_are_rejected(self):
        for extra in ({'run_mode': 'OFFICIAL'}, {'case_count': 9}):
            with self.subTest(extra=extra):
                status, body, _ = self.request('POST', PATH, dict(INPUT, **extra))
                self.assertEqual(status, 422, body)
                self.assert_no_prepared_or_executed_work()


if __name__ == '__main__':
    unittest.main()
