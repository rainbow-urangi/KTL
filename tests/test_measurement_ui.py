"""Active UI wiring tests; no prediction, generator, or M02 score recalculation."""
import json
import threading
import tempfile
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend.measurement_ui import catalog, stored_file
from backend.server import Service, make_handler

ROOT = Path(__file__).resolve().parents[1]

class MeasurementUITests(unittest.TestCase):
    def test_current_readiness_does_not_require_historical_results(self):
        config = Service().config()
        with tempfile.TemporaryDirectory() as tmp, \
             patch('backend.m02_main_web.readiness', return_value=dict(status='READY', details=dict(ground_truth_count=5))), \
             patch('backend.m03_main_web.readiness', return_value=dict(status='READY', details=dict(total_scenarios=10))), \
             patch('backend.m05_main_web.readiness', return_value=dict(status='BLOCKED', details={})), \
             patch('backend.m06_candidate.prepare', return_value=dict(status='BLOCKED', details={})):
            service = SimpleNamespace(root=Path(tmp), config=lambda: config)
            metrics = {row['metric_id']: row for row in catalog(service)['metrics']}
        for metric in ('M02', 'M03'):
            self.assertTrue(metrics[metric]['execution_available'])
            self.assertIsNone(metrics[metric]['latest'])
            self.assertIn('/run?mode=DEVELOPMENT&dataset_id=', metrics[metric]['execution_url'])
            self.assertTrue(metrics[metric]['dataset'])
        self.assertEqual(metrics['M02']['details']['ground_truth_count'], 5)
        self.assertEqual(metrics['M03']['details']['total_scenarios'], 10)

    def test_blocked_inputs_keep_their_dataset_and_reason(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('backend.m02_main_web.readiness', return_value=dict(status='BLOCKED', details={'missing':['SYNTHETIC source missing']})), \
             patch('backend.m03_main_web.readiness', return_value=dict(status='BLOCKED', details={'missing':['SYNTHETIC source changed']})), \
             patch('backend.m05_main_web.readiness', return_value=dict(status='BLOCKED', details={})), \
             patch('backend.m06_candidate.prepare', return_value=dict(status='BLOCKED', details={})):
            service = SimpleNamespace(root=Path(tmp), config=Service().config)
            metrics = {row['metric_id']: row for row in catalog(service)['metrics']}
        for metric in ('M02', 'M03'):
            self.assertFalse(metrics[metric]['execution_available'])
            self.assertTrue(metrics[metric]['dataset'])
            self.assertTrue(metrics[metric]['details']['missing'])
            self.assertIsNone(metrics[metric]['latest'])

    def test_catalog_reads_stored_results_without_legacy_assessment(self):
        with patch.object(Service, 'catalog', side_effect=AssertionError('legacy assessment forbidden')), \
             patch('backend.m02_candidate.assess', side_effect=AssertionError('M02 assessment forbidden')), \
             patch('backend.m02_recovery_candidate.assess', side_effect=AssertionError('M02 assessment forbidden')):
            metrics={x['metric_id']:x for x in catalog(Service())['metrics']}
        for metric in ('M02','M03'):
            historical = stored_file(ROOT,metric,'result.json')
            if historical.is_file():
                raw=json.loads(historical.read_text(encoding='utf-8'))
                expected=raw['overall']['score'] if metric=='M02' else raw['score']
                self.assertEqual(metrics[metric]['latest']['score'],expected)
                self.assertTrue(metrics[metric]['latest']['historical'])
            else:
                self.assertIsNone(metrics[metric]['latest'])
            self.assertTrue(metrics[metric]['execution_available'])
        for metric in ('M05','M06'):
            self.assertEqual(metrics[metric]['execution_available'], metrics[metric]['status']=='READY')
            self.assertIn('/run?mode=DEVELOPMENT',metrics[metric]['execution_url'])
        for metric in ('M01','M04','M07'):
            self.assertFalse(metrics[metric]['execution_available'])

    @patch.object(Service, 'run', side_effect=AssertionError('GET must not execute'))
    @patch('backend.m05_main_web.run', side_effect=AssertionError('GET must not run M05'))
    @patch('backend.m06_candidate.run', side_effect=AssertionError('GET must not run M06'))
    @patch('backend.m02_candidate.assess', side_effect=AssertionError('GET must not assess M02'))
    @patch('backend.m02_recovery_candidate.assess', side_effect=AssertionError('GET must not assess M02'))
    def test_http_readonly_catalog_and_original_csv_bytes(self, *guards):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Service()))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with urllib.request.urlopen(base+'/api/measurement') as response:
                metrics={x['metric_id']:x for x in json.load(response)['metrics']}
            for metric in ('M02','M03','M05','M06'):
                result=metrics[metric]['latest']
                if result is None:
                    continue
                with urllib.request.urlopen(base+result['evidence_file']) as response:
                    actual=response.read()
                path=stored_file(ROOT,metric,'evidence.csv') if metric in ('M02','M03') else ROOT/'results/development'/result['run_id']/'evidence.csv'
                self.assertEqual(actual,path.read_bytes())
            for i in range(1,8):
                with urllib.request.urlopen(base+f'/metrics/m0{i}') as response:
                    self.assertIn(b'lang="ko"',response.read())
        finally:
            server.shutdown();server.server_close();worker.join()
