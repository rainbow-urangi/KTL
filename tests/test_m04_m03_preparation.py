"""Synthetic M03 preparation/store/API contracts, never real work or GPT evidence."""
from copy import deepcopy
import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import zipfile

from backend import execution_contexts
from backend.evaluators import EvaluationError
from backend.m03_management import delete_scenario
from backend.m04.scenario_compiler import compile_code
from backend.m04.store import M04Manager
from backend.server import LocalHTTPServer, Service, make_handler
from backend.session import RuntimeSession


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def synthetic_scenario():
    identity = 'SYNTHETIC-M03-PREPARED'
    steps = [
        dict(order=1, action='open', target='http://127.0.0.1:9/synthetic',
             url='http://127.0.0.1:9/synthetic', expected_result='Synthetic page opens'),
        dict(order=2, action='input', target='#synthetic-title', value='Synthetic fresh value',
             expected_result='Synthetic title has the declared fresh value'),
    ]
    contract = dict(version=1, scenario_id=identity, steps=[
        dict(order=1, action='open', target=dict(url=steps[0]['url']),
             checks=[dict(kind='url_path', expected='/synthetic')]),
        dict(order=2, action='input', target=dict(by='css selector', value='#synthetic-title'),
             checks=[dict(kind='value', expected=steps[1]['value'])]),
    ])
    return dict(scenario_id=identity, scenario_name='Synthetic compiler preparation only',
                business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF',
                status='SUCCESS', steps=steps, execution_contract=contract,
                run_mode='DEVELOPMENT', official=False)


class ImmediateThread:
    def __init__(self, *, target, args, **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class M04M03PreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-m03-preparation-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = dict(targets=dict(M01=65, M02=75, M03=80, M04=90, M05=.79, M06=1, M07=80),
                           adapters={}, official_manifests={}, adapter_timeout_seconds=5,
                           integration_datasets={}, m03={}, m04={}, m07={})
        (self.root / 'backend').mkdir()
        (self.root / 'backend/config.json').write_bytes(encoded(self.config))
        self.session = RuntimeSession()
        self.manager = M04Manager(self.root, lambda: self.config, session=self.session)
        self.run_id = 'DEV-M03-20261113T000000-' + uuid.uuid4().hex[:12]
        self.source = synthetic_scenario()
        self.source_folder = self.root / 'results/development' / self.run_id
        self.source_folder.mkdir(parents=True)
        self.write_source()
        (self.source_folder / 'result.json').write_bytes(encoded(dict(
            run_id=self.run_id, metric_id='M03', run_mode='DEVELOPMENT', status='COMPLETED',
            score=None, official_pass=None, completed_at='2026-11-13T00:00:00+00:00',
            details=dict(evaluation_status='NOT_READY', synthetic=True))))
        self.session.claim('RESULT', self.run_id)
        self.process = self.enterContext(patch('subprocess.Popen', side_effect=AssertionError(
            'Real script/browser/model subprocess is forbidden in this synthetic regression')))
        self.provider = self.enterContext(patch('urllib.request.urlopen', side_effect=AssertionError(
            'No real HTTP provider or business site may be contacted')))
        self.enterContext(patch('backend.m04.cu02.login_configured', return_value=False))

    def tearDown(self):
        self.process.assert_not_called()
        self.provider.assert_not_called()

    def write_source(self):
        self.original = encoded(dict(run_mode='DEVELOPMENT', synthetic=True, scenarios=[self.source]))
        (self.source_folder / 'received_payload.json').write_bytes(self.original)

    def payload(self):
        return dict(m03_run_id=self.run_id, scenario_id=self.source['scenario_id'],
                    source_scenario_sha256=sha(encoded(self.source)), parameters={})

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): sha(path.read_bytes())
                for path in self.root.rglob('*') if path.is_file()}

    def prepare(self):
        return self.manager.prepare_m03(self.payload())['script']

    def queue_without_execution(self, metadata):
        started = []

        def no_execution(identity, lock):
            started.append(identity)
            lock.close()

        with patch.object(self.manager, '_execute', side_effect=no_execution), patch(
                'backend.m04.store.threading.Thread', ImmediateThread):
            job = self.manager.create(dict(script_ids=[metadata['script_id']], visible_browser=True,
                                           action_delay_ms=700, keep_open_seconds=15))['execution']
        self.assertEqual(started, [job['execution_id']])
        return job

    def test_get_descriptor_is_read_only_and_uses_current_session_source(self):
        before = self.snapshot()
        with patch.object(self.manager, 'register', side_effect=AssertionError('GET cannot register')), patch.object(
                self.manager, 'create', side_effect=AssertionError('GET cannot execute')):
            catalog = self.manager.m03_scenarios(self.run_id)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(catalog['m03_run_id'], self.run_id)
        self.assertEqual(len(catalog['scenarios']), 1)
        row = catalog['scenarios'][0]
        self.assertTrue(row['ready'])
        self.assertEqual(row['status'], 'READY')
        self.assertEqual(row['source_scenario_sha256'], sha(encoded(self.source)))
        self.assertEqual(row['source_step_count'], len(self.source['steps']))
        self.assertFalse(catalog['generated_by_llm'])

    def test_preparation_pins_all_sources_without_starting_execution_or_counting_llm(self):
        original_result = (self.source_folder / 'result.json').read_bytes()
        with patch.object(self.manager, 'create', side_effect=AssertionError('Preparation is not execution')):
            metadata = self.prepare()
        self.assertEqual((self.source_folder / 'received_payload.json').read_bytes(), self.original)
        self.assertEqual((self.source_folder / 'result.json').read_bytes(), original_result)
        self.assertEqual(metadata['source_kind'], 'M03_COMPILED_SCRIPT')
        self.assertEqual(metadata['source_m03_run_id'], self.run_id)
        self.assertFalse(metadata['generated_by_llm'])
        self.assertFalse(metadata['scripts_manually_modified'])
        self.assertTrue(metadata['business_step_required'])
        self.assertTrue(metadata['execution_ready'])
        stored, code = self.manager._script(metadata['script_id'])
        folder = self.manager.script_directory / metadata['script_id']
        self.assertEqual((folder / 'source_scenario.json').read_bytes(), encoded(self.source))
        scenario = json.loads((folder / 'execution_scenario.json').read_bytes())
        contract = json.loads((folder / 'execution_contract.json').read_bytes())
        self.assertEqual(code, compile_code(scenario, contract).encode('utf-8'))
        self.assertEqual(stored['sha256'], sha(code))
        proof = json.loads((folder / 'm03_compilation.json').read_bytes())
        for key in ('scenario_id', 'source_m03_run_id', 'source_scenario_sha256',
                    'execution_scenario_sha256', 'execution_contract_sha256', 'compiler_version'):
            self.assertEqual(proof[key], stored[key])
        self.assertEqual(proof['code_sha256'], sha(code))
        self.assertEqual(proof['source_mapping'], [
            dict(source_order=1, execution_orders=[1]), dict(source_order=2, execution_orders=[2])])
        self.assertEqual(self.manager.list_runs()['executions'], [])
        self.assertFalse(list((self.root / 'results/development').glob('latest-M04.json')))

    def test_stale_checksum_and_unexpected_payload_fields_refuse_before_registration(self):
        for change in (dict(source_scenario_sha256='0' * 64), dict(parameters={'invented': 'value'}),
                       dict(python_base64='ZmFrZQ=='), dict(visible_browser=True)):
            with self.subTest(change=list(change)):
                payload = dict(self.payload(), **change)
                before = self.snapshot()
                with patch.object(self.manager, 'register', side_effect=AssertionError('Invalid source cannot register')):
                    with self.assertRaises(EvaluationError):
                        self.manager.prepare_m03(payload)
                self.assertEqual(before, self.snapshot())

    def test_changed_original_after_selection_is_not_silently_compiled(self):
        selected = self.payload()
        self.source['steps'][1]['value'] = 'Synthetic changed source'
        self.write_source()
        before = self.snapshot()
        with self.assertRaises(EvaluationError):
            self.manager.prepare_m03(selected)
        self.assertEqual(before, self.snapshot())

    def test_failed_or_incomplete_source_never_registers_a_script(self):
        for failed in (dict(status='FAILED'), dict(steps=[])):
            with self.subTest(failed=list(failed)):
                original = deepcopy(self.source)
                self.source.update(failed)
                self.write_source()
                with patch.object(self.manager, 'register', side_effect=AssertionError('Failed source cannot register')):
                    with self.assertRaises(EvaluationError):
                        self.manager.prepare_m03(self.payload())
                self.source = original
        self.assertEqual(list(self.manager.script_directory.glob('*/script.json')), [])

    def test_deleted_and_foreign_session_sources_are_not_prepared(self):
        foreign = M04Manager(self.root, lambda: self.config, session=RuntimeSession())
        self.assertEqual(foreign.m03_scenarios()['runs'], [])
        with self.assertRaises(EvaluationError) as failure:
            foreign.prepare_m03(self.payload())
        self.assertEqual(failure.exception.status, 'SESSION_EXPIRED')
        delete_scenario(self.root, self.run_id, dict(scenario_id=self.source['scenario_id']), self.session)
        self.assertEqual(self.manager.m03_scenarios(self.run_id)['scenarios'], [])
        with self.assertRaises(EvaluationError):
            self.prepare()
        self.assertEqual((self.source_folder / 'received_payload.json').read_bytes(), self.original)

    def test_one_resolved_revision_is_frozen_even_if_current_context_changes(self):
        expected = [dict(order=row['order'], expected_result=row['expected_result']) for row in self.source['steps']]
        first = execution_contexts.save(self.root, self.run_id, self.source, self.config,
                                        self.source['execution_contract'], expected)
        register = self.manager.register
        revised = []

        def change_current_then_register(*args, **kwargs):
            changed = deepcopy(expected)
            changed[0]['expected_result'] = 'A later synthetic revision'
            revised.append(execution_contexts.save(self.root, self.run_id, self.source, self.config,
                                                   self.source['execution_contract'], changed))
            return register(*args, **kwargs)

        with patch.object(self.manager, 'register', side_effect=change_current_then_register):
            metadata = self.prepare()
        self.assertNotEqual(revised[0]['saved_revision_id'], first['saved_revision_id'])
        self.assertEqual(metadata['execution_context_revision_id'], first['saved_revision_id'])
        folder = self.manager.script_directory / metadata['script_id']
        fixed = json.loads((folder / 'execution_scenario.json').read_bytes())
        self.assertEqual(fixed['steps'][0]['expected_result'], expected[0]['expected_result'])

    def test_invalid_saved_revision_never_falls_back_to_another_binding(self):
        expected = [dict(order=row['order'], expected_result=row['expected_result']) for row in self.source['steps']]
        execution_contexts.save(self.root, self.run_id, self.source, self.config,
                                self.source['execution_contract'], expected)
        directory = execution_contexts._directory(self.root, self.run_id, self.source['scenario_id'])
        pointer = json.loads((directory / 'current.json').read_bytes())
        revision = directory / (pointer['revision_id'] + '.json')
        revision.write_bytes(revision.read_bytes() + b'\n')
        before = self.snapshot()
        with patch('backend.m04.m03_bindings.prepare', side_effect=AssertionError('No fallback from an invalid explicit revision')):
            with self.assertRaises(EvaluationError):
                self.prepare()
        self.assertEqual(self.snapshot(), before)

    def test_registered_source_contract_code_and_proof_tampering_are_rejected(self):
        for filename in ('script.py', 'source_scenario.json', 'execution_scenario.json',
                         'execution_contract.json', 'm03_compilation.json'):
            with self.subTest(filename=filename):
                metadata = self.prepare()
                path = self.manager.script_directory / metadata['script_id'] / filename
                path.write_bytes(path.read_bytes() + b'\n')
                with self.assertRaises(EvaluationError):
                    self.manager._script(metadata['script_id'])

    def test_proof_identity_is_checked_beyond_its_file_hash(self):
        metadata = self.prepare()
        folder = self.manager.script_directory / metadata['script_id']
        proof = json.loads((folder / 'm03_compilation.json').read_bytes())
        proof['scenario_id'] = 'SYNTHETIC-WRONG-IDENTITY'
        (folder / 'm03_compilation.json').write_bytes(encoded(proof))
        stored = json.loads((folder / 'script.json').read_bytes())
        stored['m03_compilation_sha256'] = sha(encoded(proof))
        (folder / 'script.json').write_bytes(encoded(stored))
        with self.assertRaises(EvaluationError):
            self.manager._script(metadata['script_id'])

    def test_only_explicit_execution_snapshots_compilation_proof_once_in_archive(self):
        metadata = self.prepare()
        folder = self.manager.script_directory / metadata['script_id']
        original_proof = (folder / 'm03_compilation.json').read_bytes()
        job = self.queue_without_execution(metadata)
        self.assertEqual(len(job['cases']), 1)
        self.assertIsNone(job['result'])
        self.assertTrue(job['visible_browser'])
        case_folder = self.manager.execution_directory / job['execution_id'] / 'CASE-001'
        self.assertEqual((case_folder / 'm03_compilation.json').read_bytes(), original_proof)
        archive = self.root / 'data/evaluation' / job['dataset_id'] / 'scripts.zip'
        with zipfile.ZipFile(io.BytesIO(archive.read_bytes())) as saved:
            name = 'CASE-001/m03_compilation.json'
            self.assertEqual(saved.namelist().count(name), 1)
            self.assertEqual(saved.read(name), original_proof)

    def test_execution_case_proof_tampering_is_rejected_before_worker_and_submission(self):
        job = self.queue_without_execution(self.prepare())
        case = job['cases'][0]
        path = self.manager.execution_directory / job['execution_id'] / case['case_id'] / 'm03_compilation.json'
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaises(EvaluationError):
            self.manager._provenance(job)
        with self.assertRaises(EvaluationError):
            self.manager._run_case(job, case)

    def test_loopback_get_and_prepare_routes_separate_registration_from_execution(self):
        service = Service(self.root, session_scoped=True)
        service.session.claim('RESULT', self.run_id)
        server = LocalHTTPServer(('127.0.0.1', 0), make_handler(service))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            def request(method, path, payload=None):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    body = None if payload is None else encoded(payload)
                    connection.request(method, path, body,
                                       {} if body is None else {'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    connection.close()
            status, catalog = request('GET', '/api/development/m04/m03-scenarios?m03_run_id=' + self.run_id)
            self.assertEqual(status, 200, catalog)
            self.assertTrue(catalog['scenarios'][0]['ready'])
            self.assertEqual(list(service.m04().script_directory.glob('*/script.json')), [])
            status, rejected = request('GET', '/api/development/m04/m03-scenarios?unknown=value')
            self.assertEqual(status, 422, rejected)
            status, rejected = request('POST', '/api/development/m04/prepare-m03',
                                       dict(self.payload(), source_scenario_sha256='0' * 64))
            self.assertEqual(status, 422, rejected)
            with patch.object(service.m04(), 'create', side_effect=AssertionError('Preparation cannot execute')):
                status, prepared = request('POST', '/api/development/m04/prepare-m03', self.payload())
            self.assertEqual(status, 201, prepared)
            self.assertTrue(prepared['script']['execution_ready'])
            self.assertFalse(prepared['generated_by_llm'])
            self.assertEqual(service.m04().list_runs()['executions'], [])
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()

    def test_binding_domain_value_error_is_not_ready_without_registering_or_replacing_other_errors(self):
        self.source['steps'] = [dict(order=1, action='NAVIGATE', target='Synthetic reviewed target')]
        self.source.pop('execution_contract')
        self.write_source()
        before = self.snapshot()
        with patch('backend.m04.m03_bindings.prepare', side_effect=ValueError('Synthetic target binding is not ready')), \
                patch.object(self.manager, 'register', side_effect=AssertionError('A rejected binding cannot register')):
            with self.assertRaises(EvaluationError) as failure:
                self.manager.prepare_m03(self.payload())
        self.assertEqual(failure.exception.status, 'NOT_READY')
        self.assertEqual(str(failure.exception), 'Synthetic target binding is not ready')
        for error in (EvaluationError('Synthetic preserved domain status', 'ERROR'), RuntimeError('Synthetic implementation failure')):
            with self.subTest(error=type(error).__name__), patch('backend.m04.m03_bindings.prepare', side_effect=error):
                with self.assertRaises(type(error)) as failure:
                    self.manager.prepare_m03(self.payload())
                self.assertIs(failure.exception, error)
        self.assertEqual(self.snapshot(), before)

    def test_loopback_binding_rejection_is_422_and_malformed_json_remains_400(self):
        self.source['steps'] = [dict(order=1, action='NAVIGATE', target='Synthetic reviewed target')]
        self.source.pop('execution_contract')
        self.write_source()
        service = Service(self.root, session_scoped=True)
        service.session.claim('RESULT', self.run_id)
        server = LocalHTTPServer(('127.0.0.1', 0), make_handler(service))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        before = self.snapshot()
        try:
            def request(raw):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    connection.request('POST', '/api/development/m04/prepare-m03', raw,
                                       {'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    connection.close()
            with patch('backend.m04.m03_bindings.prepare', side_effect=ValueError('Synthetic target binding is not ready')) as binding, \
                    patch.object(service.m04(), 'register', side_effect=AssertionError('A rejected binding cannot register')), \
                    patch.object(service.m04(), 'create', side_effect=AssertionError('A rejected binding cannot execute')):
                status, rejected = request(encoded(self.payload()))
                self.assertEqual(status, 422, rejected)
                self.assertEqual(rejected, dict(status='NOT_READY', error='Synthetic target binding is not ready'))
                binding.assert_called_once()
                status, rejected = request(b'{"m03_run_id":')
                self.assertEqual(status, 400, rejected)
                self.assertEqual(rejected, dict(status='ERROR', error='Invalid JSON or Content-Length'))
                binding.assert_called_once()
            self.assertEqual(service.m04().list_runs()['executions'], [])
            self.assertEqual(list(service.m04().script_directory.glob('*/script.json')), [])
            self.assertEqual(self.snapshot(), before)
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()


if __name__ == '__main__':
    unittest.main()
