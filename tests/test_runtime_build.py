"""Synthetic source drift and real loopback handler checks; writes remain in temp roots."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.evaluators import EvaluationError
from backend.runtime_build import RuntimeBuild
from backend.server import LocalHTTPServer, ROOT, Service, make_handler


class RuntimeBuildTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ktl-runtime-build-synthetic-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.backend = self.root / 'synthetic-source'
        (self.backend / 'm07').mkdir(parents=True)
        (self.backend / 'server.py').write_bytes(b'# synthetic server\n')
        (self.backend / 'm07/generator.py').write_bytes(b'# synthetic provider\n')

    def test_inventory_detects_changed_added_removed_sources_and_new_build(self):
        inventory = RuntimeBuild(self.backend)
        self.assertEqual(set(inventory.startup), {'server.py', 'm07/generator.py'})
        self.assertTrue(inventory.status()['source_current'])
        (self.backend / 'config.json').write_bytes(b'{"synthetic":true}')
        (self.backend / '.env.local').write_bytes(b'SYNTHETIC_SECRET=not-a-real-key')
        self.assertTrue(inventory.status()['source_current'])
        (self.backend / 'server.py').write_bytes(b'# changed synthetic source\n')
        (self.backend / 'm07/generator.py').unlink()
        (self.backend / 'm07/new.py').write_bytes(b'# additive synthetic source\n')
        status = inventory.status()
        self.assertFalse(status['source_current'])
        self.assertEqual(status['changed_source_files'], ['server.py'])
        self.assertEqual(status['added_source_files'], ['m07/new.py'])
        self.assertEqual(status['removed_source_files'], ['m07/generator.py'])
        restarted = RuntimeBuild(self.backend)
        self.assertTrue(restarted.status()['source_current'])
        self.assertNotEqual(restarted.build_id, inventory.build_id)

    def test_unreadable_or_absent_source_cannot_report_current(self):
        inventory = RuntimeBuild(self.backend)
        with patch.object(Path, 'read_bytes', side_effect=PermissionError('Synthetic unreadable source')):
            self.assertFalse(inventory.status()['source_current'])
            self.assertFalse(RuntimeBuild(self.backend).status()['source_current'])
        self.assertFalse(RuntimeBuild(self.root / 'absent-source').status()['source_current'])

    def test_linked_source_is_rejected_without_reading_link_destination(self):
        inventory = RuntimeBuild(self.backend)
        original_read = Path.read_bytes
        touched = []
        def read(path):
            touched.append(path)
            return original_read(path)
        with patch.object(Path, 'is_symlink', lambda path: path.name == 'generator.py'), \
                patch.object(Path, 'read_bytes', read):
            status = inventory.status()
        self.assertFalse(status['source_current'])
        self.assertIn('@link/m07/generator.py', status['added_source_files'])
        self.assertNotIn(self.backend / 'm07/generator.py', touched)

    def test_service_inventory_uses_installed_code_not_data_backend(self):
        service = Service(self.root)
        self.assertEqual(service.runtime_build.directory, (ROOT / 'backend').resolve())
        self.assertIn('m07/generator.py', service.startup_source_sha256)
        self.assertIn('m07/store.py', service.startup_source_sha256)
        from backend.m07.generator import PROMPT_VERSION
        self.assertEqual(service.health()['m07_prompt_version'], PROMPT_VERSION)
        self.assertFalse((self.root / 'data').exists())

    def test_stale_http_blocks_new_work_but_allows_health_history_and_cancel(self):
        service = Service(self.root)
        service.runtime_build = RuntimeBuild(self.backend)
        manager = Mock()
        manager.list_runs.return_value = {'runs': []}
        manager.cancel.return_value = {'status': 'CANCELLED'}
        service._m07 = manager
        server = LocalHTTPServer(('127.0.0.1', 0), make_handler(service))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        def stop():
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
        self.addCleanup(stop)
        port = server.server_address[1]

        def request(method, route, payload=None):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            try:
                conn.request(method, route, None if payload is None else json.dumps(payload),
                             {} if payload is None else {'Content-Type': 'application/json'})
                reply = conn.getresponse()
                return reply.status, json.loads(reply.read())
            finally:
                conn.close()
        self.assertEqual(request('GET', '/api/health')[1]['status'], 'READY')
        (self.backend / 'm07/generator.py').write_bytes(b'# changed during synthetic run\n')
        self.assertEqual(request('GET', '/api/health')[1]['status'], 'RESTART_REQUIRED')
        run = 'M07-GEN-' + 'a' * 32
        for route in ('/api/development/m07/generations', '/api/m03/generate',
                      '/api/development/m04/scripts', '/api/development/m04/executions',
                      f'/api/development/m07/generations/{run}/validate',
                      f'/api/development/m07/generations/{run}/export-m04'):
            code, result = request('POST', route, {})
            self.assertEqual(code, 409, route)
            self.assertEqual(result['status'], 'RESTART_REQUIRED')
        manager.create.assert_not_called()
        self.assertEqual(request('GET', '/api/development/m07/generations'), (200, {'runs': []}))
        self.assertEqual(request('POST', f'/api/development/m07/generations/{run}/cancel', {}),
                         (200, {'status': 'CANCELLED'}))
        manager.cancel.assert_called_once_with(run)
        # A newly discovered provider block must reach an already-open UI too.
        (self.backend / 'm07/generator.py').write_bytes(b'# synthetic provider\n')
        manager.create.side_effect = EvaluationError('Synthetic provider cooldown', 'NOT_READY')
        provider = dict(blocked=True, reason='HTTP_429_COOLDOWN', next_eligible_at='2099-01-01T00:00:00+00:00')
        manager.current_provider_state.return_value = provider
        code, response = request('POST', '/api/development/m07/generations', {})
        self.assertEqual(code, 422)
        self.assertEqual(response['provider_state'], provider)


if __name__ == '__main__':
    unittest.main()
