"""정상 CLI/HTTP/subprocess를 사용한 합성 시험. 모든 쓰기는 temp root에 격리한다."""
import hashlib
import http.client
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.evaluators import call_adapter
from backend.server import ROOT


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8'))


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()


class RuntimeIsolationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-runtime-isolation-')
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name).resolve()
        self.root = self.fixture(self.temp / 'runtime-one')
        self.request = dict(business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF',
                            run_mode='DEVELOPMENT', generator_mode='REAL', dataset_id='isolation-input')

    def fixture(self, root):
        folder = root / 'data/evaluation/isolation-input'
        folder.mkdir(parents=True)
        canonical = folder / 'canonical.json'
        models = folder / 'process_models.csv'
        write_json(canonical, [dict(schema_version='workflow-canonical-1.1', process_model_id='SYNTHETIC-PM',
                                   procedures=[dict(id='SYNTHETIC-NODE', order=1, action='selection',
                                                    target=dict(page_path='/synthetic', role='button', normalized_endpoint=''),
                                                    evidence=['SYNTHETIC-EVENT'])])])
        models.write_bytes(b'process_model_id,canonical_instance_id,mode\nSYNTHETIC-PM,SYNTHETIC-WF,DEVELOPMENT\n')
        manifest = dict(dataset_id='isolation-input', metric_id='M03', run_mode='DEVELOPMENT',
                        source_type='DEVELOPMENT', data_class='DEVELOPMENT', official=False, synthetic=False,
                        files=[dict(path=p.name, sha256=file_sha(p)) for p in (canonical, models)])
        write_json(folder / 'manifest.json', manifest)
        definition = dict(business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF', business_name='Synthetic isolation fixture',
                          start_screen='https://example.invalid/synthetic', required_procedures=['Synthetic observed procedure'],
                          end_condition='Synthetic outcome', canonical_process_model_id='SYNTHETIC-PM',
                          canonical_instance_id='SYNTHETIC-WF', canonical_input_path=canonical.relative_to(root).as_posix(),
                          canonical_models_path=models.relative_to(root).as_posix())
        config = dict(targets={f'M0{i}': value for i, value in enumerate((65, 80, 80, 90, .8, 1, 80), 1)},
                      adapters={'scenario_generation': [sys.executable, '-B', '-m', 'backend.m03_canonical_adapter']},
                      official_manifests={}, adapter_timeout_seconds=15,
                      integration_datasets={'isolation-input': dict(run_mode='DEVELOPMENT', manifest='data/evaluation/isolation-input/manifest.json')},
                      m03=dict(generator_mode='REAL', transport='SUBPROCESS', source_module='synthetic-isolation-fixture',
                               source_version='v1', input_manifest='data/evaluation/isolation-input/manifest.json',
                               business_units=[definition]))
        write_json(root / 'backend/config.json', config)
        return root

    def adapter_payload(self):
        config = json.loads((self.root / 'backend/config.json').read_text(encoding='utf-8'))
        folder = self.root / 'data/evaluation/isolation-input'
        return dict(business_unit_id=self.request['business_unit_id'], workflow_id=self.request['workflow_id'],
                    business_definition=config['m03']['business_units'][0],
                    analysis_input=dict(files=[dict(path=p.relative_to(self.root).as_posix(), sha256=file_sha(p))
                                               for p in (folder / 'canonical.json', folder / 'process_models.csv')]))

    @contextmanager
    def server(self, root):
        # Launch the shipped entrypoint; do not substitute a custom Service or handler.
        process = subprocess.Popen([sys.executable, '-B', '-m', 'backend.server', '--root', str(root), '--port', '0'],
                                   cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding='utf-8', env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        ready = queue.Queue()
        threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
        try:
            line = ready.get(timeout=10).strip()
            found = re.fullmatch(r'Rainbow KTL: http://127\.0\.0\.1:([0-9]+)', line)
            self.assertIsNotNone(found, 'CLI must flush its actual bound address')
            port = int(found[1])
            self.assertGreater(port, 0)
            self.assertNotEqual(port, 8000)
            yield port
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)

    @staticmethod
    def request_http(port, method, route, payload=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        try:
            connection.request(method, route, body, {'Content-Type': 'application/json'} if body else {})
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode('utf-8'))
        finally:
            connection.close()

    def generate_and_ingest(self, port, root):
        code, generated = self.request_http(port, 'POST', '/api/m03/generate', self.request)
        self.assertEqual(code, 200, generated)
        self.assertEqual(generated['status'], 'SUCCESS')
        self.assertEqual(len(generated['steps']), 1)
        payload = dict(external_run_id='SAME-SYNTHETIC-EXTERNAL-ID', dataset_id=self.request['dataset_id'],
                       run_mode='DEVELOPMENT', source_module=generated['source_module'], source_version=generated['source_version'],
                       submitted_at=datetime.now(timezone.utc).isoformat(),
                       dataset_manifest_sha256=file_sha(root / 'data/evaluation/isolation-input/manifest.json'),
                       scenarios=[generated], details={})
        code, result = self.request_http(port, 'POST', '/api/integrations/m03/result', payload)
        self.assertEqual(code, 201, result)
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(result['details']['evaluation_status'], 'NOT_READY')
        self.assertIsNone(result['score'])
        self.assertIsNone(result['official_pass'])
        receipt = root / 'results/m03_generations' / generated['origin_generation_id']
        self.assertTrue(all((receipt / name).is_file() for name in ('started.json', 'receipt.json', 'response.json')))
        archive = root / 'results/development' / result['run_id']
        self.assertEqual(json.loads((archive / 'received_payload.json').read_text(encoding='utf-8')), payload)
        latest = json.loads((root / 'results/development/latest-M03.json').read_text(encoding='utf-8'))
        self.assertEqual(latest['run_id'], result['run_id'])
        self.assertEqual(len(list((root / 'results/integrations').glob('*.json'))), 1)
        code, history = self.request_http(port, 'GET', '/api/development/m03/runs')
        self.assertEqual(code, 200)
        self.assertEqual([row['run_id'] for row in history['runs']], [result['run_id']])
        return payload, result

    def test_shipped_CLI_HTTP_subprocess_and_storage_do_not_write_installed_project(self):
        protected = [ROOT / 'backend/config.json']
        for relative in ('data', 'results'):
            protected.extend(p for p in (ROOT / relative).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        before = {p.relative_to(ROOT).as_posix(): file_sha(p) for p in protected}
        with self.server(self.root) as port:
            self.generate_and_ingest(port, self.root)
        current_paths = [ROOT / 'backend/config.json']
        for relative in ('data', 'results'):
            current_paths.extend(p for p in (ROOT / relative).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        after = {p.relative_to(ROOT).as_posix(): file_sha(p) for p in current_paths}
        self.assertEqual(after, before, 'CLI trial must not write installed config, results, pointers or data')

    def test_two_roots_keep_receipts_reservations_latest_and_sessions_separate(self):
        other = self.fixture(self.temp / 'runtime-two')
        with self.server(self.root) as first, self.server(other) as second:
            first_health = self.request_http(first, 'GET', '/api/health')[1]
            second_health = self.request_http(second, 'GET', '/api/health')[1]
            self.assertNotEqual(first_health['server_session_id'], second_health['server_session_id'])
            payload, first_result = self.generate_and_ingest(first, self.root)
            self.assertFalse((other / 'results').exists())
            self.assertEqual(self.request_http(second, 'GET', '/api/development/m03/runs')[1]['runs'], [])
            _, second_result = self.generate_and_ingest(second, other)
            self.assertNotEqual(first_result['run_id'], second_result['run_id'])
            self.assertEqual(self.request_http(first, 'POST', '/api/integrations/m03/result', payload)[0], 409)
        with self.server(self.root) as restarted:
            self.assertEqual(self.request_http(restarted, 'GET', '/api/development/m03/runs')[1]['runs'], [])
            self.assertEqual(self.request_http(restarted, 'POST', '/api/integrations/m03/result', payload)[0], 409)

    def test_adapter_env_root_overrides_inherited_root_and_imports_installed_code(self):
        probe = ('import json,os,pathlib,backend.m03_canonical_adapter as adapter; '
                 'print(json.dumps(dict(root=os.environ["KTL_RUNTIME_ROOT"],cwd=os.getcwd(),'
                 'code=str(pathlib.Path(adapter.__file__).resolve()),payload=json.load(__import__("sys").stdin))))')
        config = dict(adapters={'scenario_generation': [sys.executable, '-B', '-c', probe]})
        payload = {'business_unit_id': 'SYNTHETIC-BU'}
        with patch.dict(os.environ, {'KTL_RUNTIME_ROOT': str(self.temp / 'wrong-root')}):
            result = call_adapter(config, 'scenario_generation', payload, self.root)
        self.assertEqual(result['root'], str(self.root))
        self.assertEqual(result['cwd'], str(self.root))
        self.assertEqual(Path(result['code']), ROOT / 'backend/m03_canonical_adapter.py')
        self.assertEqual(result['payload'], payload)

    def test_adapter_standalone_module_uses_explicit_env_root_without_backend_copy(self):
        env = {**os.environ, 'KTL_RUNTIME_ROOT': str(self.root), 'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}
        result = subprocess.run([sys.executable, '-B', '-m', 'backend.m03_canonical_adapter'], cwd=self.temp,
                                input=json.dumps(self.adapter_payload()).encode(), capture_output=True, timeout=10, env=env)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        self.assertEqual(json.loads(result.stdout)['workflow_id'], 'SYNTHETIC-WF')
        self.assertFalse((self.root / 'backend/m03_canonical_adapter.py').exists())

    def test_invalid_explicit_adapter_env_does_not_fall_back_to_installed_root(self):
        for bad in ('', str(self.temp / 'missing')):
            with self.subTest(empty=not bad):
                env = {**os.environ, 'KTL_RUNTIME_ROOT': bad, 'PYTHONPATH': str(ROOT)}
                result = subprocess.run([sys.executable, '-B', '-m', 'backend.m03_canonical_adapter'], cwd=self.temp,
                                        input=b'{}', capture_output=True, timeout=10, env=env)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(result.stdout)
                self.assertIn(b'could not validate', result.stderr)

    def test_server_rejects_missing_explicit_root_or_config_before_binding(self):
        empty = self.temp / 'empty-project'
        empty.mkdir()
        for root in (self.temp / 'missing-project', empty):
            with self.subTest(root=root.name):
                result = subprocess.run([sys.executable, '-B', '-m', 'backend.server', '--root', str(root), '--port', '0'],
                                        cwd=ROOT, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(b'Rainbow KTL:', result.stdout)
                self.assertFalse((root / 'results').exists())
                self.assertFalse((root / 'data').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
