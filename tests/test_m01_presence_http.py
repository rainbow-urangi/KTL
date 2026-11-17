"""Real loopback API checks with temporary synthetic collection data only."""
import base64
import csv
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.server import LocalHTTPServer, Service, make_handler


class M01PresenceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / 'backend').mkdir()
        config = Path(__file__).resolve().parents[1] / 'backend/config.json'
        (self.root / 'backend/config.json').write_bytes(config.read_bytes())
        self.service = Service(self.root, session_scoped=True)
        self.server = LocalHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def request(self, path, payload=None):
        encoded = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.base + path, data=encoded,
                          headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=20) as response:
            return response.status, response.read(), response.headers

    def upload(self):
        columns = ['event_id', 'session_id', 'event_time', 'event_type', 'page_url',
                   'page_title', 'target_key', 'interaction_type', 'target_selector']
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerow(dict(event_id='synthetic-navigation', session_id='synthetic-session',
                             event_time='2026-11-16T00:00:00.000Z', event_type='PAGE_VIEW',
                             page_url='https://rainbowlab.ai.kr/mypage/schedule',
                             page_title='Synthetic schedule', target_key='html',
                             interaction_type='route_change', target_selector='html'))
        status, raw, _ = self.request('/api/development/m01/csv', dict(
            filename='synthetic.csv', csv_base64=base64.b64encode(output.getvalue().encode()).decode()))
        self.assertEqual(status, 201)
        return json.loads(raw)

    def test_twenty_scenarios_save_verifiable_results_and_restore_without_legacy_truth(self):
        _, raw, _ = self.request('/api/development/m01/scenarios')
        catalog = json.loads(raw)
        self.assertEqual(len(catalog['scenarios']), 20)
        uploaded = self.upload()
        dataset = uploaded['dataset']['dataset_id']
        status, raw, _ = self.request('/api/development/m01/compare-scenarios', dict(
            dataset_id=dataset, catalog_version=catalog['version'], catalog_sha256=catalog['sha256']))
        self.assertEqual(status, 201)
        batch = json.loads(raw)
        self.assertEqual(len(batch['candidates']), 20)
        self.assertTrue(all(row['status'] == 'COMPLETED' for row in batch['candidates']))
        for row in batch['candidates']:
            result = row['result']
            self.assertEqual(result['session_id'], 'synthetic-session')
            self.assertIsNone(result['official_pass'])
            path = '/api/development/m01/comparisons/' + result['comparison_id']
            _, stored, _ = self.request(path)
            self.assertEqual(json.loads(stored)['presence_truth'], row['truth'])
            _, proof, _ = self.request(path + '/verification')
            self.assertIs(json.loads(proof)['verified'], True)
            _, event_rows, headers = self.request(path + '/event-results.csv')
            self.assertIn('text/csv', headers['Content-Type'])
            self.assertEqual(len(list(csv.DictReader(io.StringIO(event_rows.decode('utf-8-sig'))))),
                             result['summary']['expected_count'])
            _, readable, readable_headers = self.request(path + '/ktl-evidence.csv')
            self.assertTrue(readable.startswith(b'\xef\xbb\xbf'))
            self.assertIn('M01-ktl-evidence.csv', readable_headers['Content-Disposition'])
            report_rows = list(csv.DictReader(io.StringIO(readable.decode('utf-8-sig'))))
            self.assertEqual(sum(row['구분'] == '이벤트' for row in report_rows),
                             result['summary']['expected_count'])

    def test_changed_catalog_is_rejected_before_comparisons_are_saved(self):
        uploaded = self.upload()
        _, raw, _ = self.request('/api/development/m01/scenarios')
        catalog = json.loads(raw)
        with self.assertRaises(HTTPError) as caught:
            self.request('/api/development/m01/compare-scenarios', dict(
                dataset_id=uploaded['dataset']['dataset_id'], catalog_version=catalog['version'],
                catalog_sha256='0' * 64))
        self.assertEqual(caught.exception.code, 422)
        directory = self.root / 'data/development/m01_comparisons'
        self.assertFalse(directory.exists() and any(directory.iterdir()))


if __name__ == '__main__':
    unittest.main()
