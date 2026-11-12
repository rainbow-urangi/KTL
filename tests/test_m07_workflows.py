"""Prepared workflow evidence uses temporary fixtures, with no site or LLM calls."""
import ast
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from backend.evaluators import EvaluationError
from backend.m04.checks import prepare_contract
from backend.m07 import workflows
from backend.m07.store import M07Manager
from backend.session import RuntimeSession


LOGIN = dict(KTL_M04_RBEM_USERNAME='SYNTHETIC_WORKFLOW_ACCOUNT',
             KTL_M04_RBEM_PASSWORD='SYNTHETIC_WORKFLOW_PASSWORD')
PARAMETERS = dict(date='2028-02-29', title='SYNTHETIC new title', description='SYNTHETIC temporary contents',
                  contact_name='SYNTHETIC contact', company='SYNTHETIC company', phone='01012345678',
                  email='synthetic@example.invalid', lookup_title='', cases_per_workflow=2)
IDS = [f'CU{number:02d}' for number in range(1, 11)]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class PreparedWorkflowsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-m07-workflows-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.enterContext(patch.dict(os.environ, dict(LOGIN, OPENAI_API_KEY='', KTL_M07_OPENAI_API_KEY='', KTL_M07_MODEL='')))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No test subprocess/browser')))
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No test network')))
        self.enterContext(patch('urllib.request.urlopen', side_effect=AssertionError('No test HTTP/LLM')))
        self.config = dict(targets={'M07': 80}, m07={}, m04={}, integration_datasets={})
        self.generator = Mock(side_effect=AssertionError('Prepared work must never call an LLM'))
        self.manager = M07Manager(self.root, lambda: deepcopy(self.config), generator=self.generator, session=RuntimeSession())
        self.manager._readiness = lambda: dict(selenium=True, chrome=True, edge=False, message='SYNTHETIC READY')
        self.enterContext(patch.object(self.manager, '_launch', side_effect=self.launch_synchronously))

    def launch_synchronously(self, identity, phase, run_lock, browser_lock=None):
        self.manager._work(identity, phase, run_lock, browser_lock)

    def prepare(self, identities=None, values=None):
        response = self.manager.prepare_workflows(dict(workflow_ids=identities or IDS,
                                                       parameters=deepcopy(PARAMETERS if values is None else values)))
        job = self.manager.read(response['generation']['generation_id'])['generation']
        self.assertEqual(job['status'], 'GENERATED', job.get('error'))
        return job

    def snapshot(self):
        return {str(path.relative_to(self.root)): digest(path.read_bytes()) for path in self.root.rglob('*') if path.is_file()}

    def test_catalog_is_read_only_and_lists_all_ten_workflows_with_explicit_prepared_origin(self):
        before = self.snapshot()
        value = self.manager.workflows()
        self.assertEqual([row['workflow_id'] for row in value['workflows']], IDS)
        self.assertTrue(all(row['available'] and row['steps'] for row in value['workflows']))
        self.assertEqual(value['browser'], 'chrome')
        self.assertEqual(value['code_source'], 'PREPARED')
        self.assertIs(value['generated_by_llm'], False)
        self.assertTrue(value['login_configured'])
        self.assertEqual(value['defaults']['cases_per_workflow'], 2)
        self.assertEqual(value['run_mode'], 'DEVELOPMENT')
        self.assertEqual(self.snapshot(), before)
        value['workflows'][0]['steps'].clear()
        self.assertTrue(self.manager.workflows()['workflows'][0]['steps'])
        for secret in LOGIN.values():
            self.assertNotIn(secret, json.dumps(value))

    def test_invalid_workflow_ids_and_parameters_are_rejected_without_prepared_jobs(self):
        invalid = [None, {}, dict(workflow_ids=[], parameters=PARAMETERS),
                   dict(workflow_ids=['CU11'], parameters=PARAMETERS),
                   dict(workflow_ids=['CU01', 'CU01'], parameters=PARAMETERS),
                   dict(workflow_ids='CU01', parameters=PARAMETERS),
                   dict(workflow_ids=[None], parameters=PARAMETERS),
                   dict(workflow_ids=IDS, parameters=PARAMETERS, run_mode='OFFICIAL')]
        changes = [dict(date='2027-02-29'), dict(title='x' * 91), dict(description=' '),
                   dict(phone='bad'), dict(email='invalid'), dict(contact_name=''), dict(company=''),
                   dict(cases_per_workflow=0), dict(cases_per_workflow=3), dict(cases_per_workflow=True),
                   dict(target_url='https://example.invalid/override'), dict(browser='edge'),
                   dict(lookup_title='bad\nline'), dict(contact_name='bad\x00value')]
        invalid += [dict(workflow_ids=['CU02'], parameters=dict(PARAMETERS, **change)) for change in changes]
        for payload in invalid:
            with self.subTest(payload_type=type(payload).__name__), self.assertRaises(EvaluationError):
                self.manager.prepare_workflows(payload)
        self.assertEqual(list(self.manager.execution_directory.iterdir()), [])
        self.generator.assert_not_called()

    def test_missing_login_is_explicit_and_does_not_create_a_generation(self):
        with patch.dict(os.environ, {key: '' for key in LOGIN}):
            self.assertFalse(self.manager.workflows()['login_configured'])
            with self.assertRaises(EvaluationError) as failure:
                self.manager.prepare_workflows(dict(workflow_ids=['CU02'], parameters=PARAMETERS))
        self.assertEqual(failure.exception.status, 'NOT_CONFIGURED')
        self.assertEqual(list(self.manager.execution_directory.iterdir()), [])

    def test_twenty_originals_have_chrome_contracts_sources_and_verified_display_identity(self):
        original = deepcopy(PARAMETERS)
        job = self.prepare()
        self.assertEqual(PARAMETERS, original)
        self.assertEqual(len(job['cases']), 20)
        self.assertEqual(job['workflow_ids'], IDS)
        self.assertEqual(job['code_source'], 'PREPARED')
        self.assertIs(job['generated_by_llm'], False)
        self.assertEqual(job['browser'], 'chrome')
        self.assertTrue(job['visible_browser'])
        self.assertIsNone(job.get('measurement'))
        self.assertIsNone(job['result'])
        self.assertEqual(job['counts']['generation_request_count'], 20)
        self.assertEqual(job['counts']['generated_code_count'], 20)
        self.assertEqual(job['counts']['both_pass_count'], 0)
        self.assertEqual([case['case_id'] for case in job['cases']], [f'CASE-{number:03d}' for number in range(1, 21)])
        self.assertEqual(len({case['scenario_id'] for case in job['cases']}), 20)
        folder = self.manager.execution_directory / job['generation_id']
        archive_raw = (folder / 'code.zip').read_bytes()
        self.assertEqual(digest(archive_raw), job['archive_sha256'])
        with zipfile.ZipFile(folder / 'code.zip') as archive:
            for index, case in enumerate(job['cases']):
                self.assertEqual(case['workflow_id'], IDS[index // 2])
                self.assertEqual(case['workflow_case_number'], index % 2 + 1)
                self.assertEqual(case['source_kind'], 'RBEM_PREPARED_WORKFLOW')
                self.assertEqual(case['browser'], 'chrome')
                self.assertIsNone(case['source_m03_run_id'])
                self.assertIs(case['generated_by_llm'], False)
                for key in ('generation_invoked', 'generation_http_attempted', 'provider_response_observed'):
                    self.assertIs(case[key], False)
                self.assertEqual(case['generation_status'], 'PASS')
                case_folder = folder / case['case_id']
                source = (case_folder / 'prepared_code.py').read_bytes()
                self.assertEqual(source, (case_folder / 'script.py').read_bytes())
                self.assertEqual(digest(source), case['source_file_sha256'])
                tree = ast.parse(source)
                self.assertTrue(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))
                self.assertIn(b'webdriver.Chrome(', source)
                self.assertNotIn(b'webdriver.Edge(', source)
                scenario = json.loads((case_folder / 'execution_scenario.json').read_bytes())
                contract = json.loads((case_folder / 'execution_contract.json').read_bytes())
                self.assertEqual(prepare_contract(scenario), contract)
                for name in ('script.py', 'prepared_code.py', 'prepared_source.json', 'source_scenario.json',
                             'execution_scenario.json', 'execution_contract.json',
                             'workflow_definition.json', 'workflow_parameters.json'):
                    self.assertEqual(archive.read(case['case_id'] + '/' + name), (case_folder / name).read_bytes())
                for name, expected in case['source_workflow_files'].items():
                    self.assertEqual(digest((case_folder / name).read_bytes()), expected)
                display = self.manager.code(job['generation_id'], case['case_id'])
                self.assertEqual(display['code'].encode('utf-8'), source)
                self.assertEqual(base64.b64decode(display['code_base64']), source)
                self.assertEqual(display['identity_verification'], dict(verified=True, source_sha256=digest(source), display_sha256=digest(source)))
                self.assertFalse((case_folder / 'response.json').exists())
                self.assertFalse((case_folder / 'prompt.json').exists())
        self.generator.assert_not_called()

    def test_one_case_per_selected_workflow_uses_new_inputs_without_modifying_older_originals(self):
        first = self.prepare(['CU02'], dict(PARAMETERS, cases_per_workflow=1))
        folder = self.manager.execution_directory / first['generation_id']
        original = (folder / 'CASE-001/script.py').read_bytes()
        second = self.prepare(['CU02'], dict(PARAMETERS, title='SYNTHETIC changed', cases_per_workflow=1))
        self.assertEqual(len(second['cases']), 1)
        self.assertNotEqual(first['cases'][0]['scenario_id'], second['cases'][0]['scenario_id'])
        self.assertEqual((folder / 'CASE-001/script.py').read_bytes(), original)

    def test_workflow_definition_parameters_and_code_tampering_refuse_display_and_validation(self):
        for name in ('workflow_definition.json', 'workflow_parameters.json', 'prepared_code.py', 'script.py', 'execution_contract.json'):
            with self.subTest(name=name):
                job = self.prepare(['CU02'], dict(PARAMETERS, cases_per_workflow=1))
                folder = self.manager.execution_directory / job['generation_id'] / 'CASE-001'
                path = folder / name
                path.write_bytes(path.read_bytes() + b'\n')
                with self.assertRaises(EvaluationError):
                    self.manager.code(job['generation_id'], 'CASE-001')
                called = []
                with patch.object(self.manager, '_run_case', side_effect=lambda *args: called.append(True)):
                    self.manager.validate(job['generation_id'])
                saved = self.manager.read(job['generation_id'])['generation']
                self.assertEqual(saved['status'], 'ERROR')
                self.assertIsNone(saved['result'])
                self.assertEqual(called, [])

    def test_sixteen_passes_and_four_failures_keep_twenty_case_denominator_without_llm_evidence(self):
        job = self.prepare()
        calls = []
        def synthetic_execution(current, case):
            calls.append(case['case_id'])
            if case['case_id'] == 'CASE-020':
                raise RuntimeError('SYNTHETIC BROWSER START ERROR')
            failed = int(case['case_id'][-3:]) >= 17
            case.update(status='FAIL' if failed else 'PASS', browser_started=True,
                        business_step_complete=not failed, independent_checks_passed=not failed,
                        error='SYNTHETIC EXPECTED STATE MISMATCH' if failed else None)
        with patch.object(self.manager, '_run_case', side_effect=synthetic_execution), patch('backend.m07.store.ingest') as ingest:
            self.manager.validate(job['generation_id'])
        done = self.manager.read(job['generation_id'])['generation']
        self.assertEqual(done['status'], 'COMPLETED', done.get('error'))
        self.assertEqual(len(calls), 20)
        self.assertEqual(done['counts']['generated_code_count'], 20)
        self.assertEqual(done['counts']['syntax_pass_count'], 20)
        self.assertEqual(done['counts']['both_pass_count'], 16)
        self.assertEqual(done['cases'][-1]['execution_status'], 'ERROR')
        self.assertEqual([case['final_status'] for case in done['cases']], ['PASS'] * 16 + ['FAIL'] * 4)
        self.assertEqual(done['result']['score'], 80)
        self.assertEqual(done['result']['sample_count'], 20)
        self.assertEqual(done['result']['details']['denominator'], 20)
        self.assertIs(done['result']['details']['generated_by_llm'], False)
        self.assertIsNone(done['result']['official_pass'])
        self.assertEqual(done['result']['provenance']['code_source'], 'PREPARED')
        self.generator.assert_not_called()
        ingest.assert_not_called()


if __name__ == '__main__':
    unittest.main()
