"""Sandbox samples call the unchanged ingestion API with temporary mock fixtures."""
import copy
import http.client
import json
import shutil
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from http.server import ThreadingHTTPServer
from backend.server import Service, make_handler
from backend.evaluators import digest

ROOT=Path(__file__).resolve().parents[1]

class IntegrationSandboxTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'backend').mkdir()
        shutil.copy(ROOT/'backend/config.json',self.root/'backend/config.json')
        shutil.copytree(ROOT/'frontend',self.root/'frontend')
        shutil.copytree(ROOT/'data/evaluation/mock-dataset-01',self.root/'data/evaluation/mock-dataset-01')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Service(self.root)))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.samples=json.loads((self.root/'frontend/integration-samples.json').read_text())['samples']
    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.server_close();self.temp.cleanup()
    def request(self,method,path,body=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        c.request(method,path,json.dumps(body) if body is not None else None,{'Content-Type':'application/json'})
        r=c.getresponse();status=r.status;content=r.read();c.close();return status,content
    def test_page_and_assets(self):
        for path,needle in [('/developer/integration-api',b'Developer Integration Sandbox'),('/integration-sandbox.js',b'Send Test Request'),('/integration-sandbox.css',b'.api-card'),('/integration-samples.json',b'M01')]:
            status,content=self.request('GET',path);self.assertEqual(status,200);self.assertIn(needle,content)
    def test_all_samples_real_http_counts_and_official_null(self):
        expected={'M03':80,'M04':90,'M07':80}
        for sample in self.samples:
            metric=sample['metric_id'];payload=copy.deepcopy(sample['request']);payload['external_run_id']+='-'+uuid.uuid4().hex
            self.assertNotIn('score',payload)
            self.assertEqual(payload['dataset_manifest_sha256'],digest(self.root/'data/evaluation/mock-dataset-01/data_manifest.json'))
            status,raw=self.request('POST',sample['endpoint'],payload);result=json.loads(raw)
            self.assertEqual(status,201,result);self.assertEqual(result['status'],'COMPLETED')
            self.assertAlmostEqual(result['score'],expected[metric]);self.assertIsNone(result['official_pass']);self.assertIsNone(result['pass'])
            if metric!='M03':self.assertEqual(result['details']['raw_counts'],payload['counts'])
            self.assertEqual(result['run_mode'],'REFERENCE')
            self.assertEqual(result['provenance']['source_module'],payload['source_module'])
            # The existing central evaluator, not the sample response, determines score.
            changed=copy.deepcopy(payload);changed['external_run_id']+='-changed'
            if metric=='M03':del changed['scenarios'][0]['steps'][0]['action']
            elif metric=='M04':
                changed['counts']['successful_execution_count']-=1
                changed['counts']['failed_execution_count']+=1
            else:
                changed['counts']['both_pass_count']-=1
                changed['counts']['syntax_pass_count']-=1
                changed['cases'][0]['syntax_status']='FAIL'
                changed['cases'][0]['final_status']='FAIL'
            status,raw=self.request('POST',sample['endpoint'],changed)
            self.assertEqual(status,201);self.assertLess(json.loads(raw)['score'],result['score'])
            status,_=self.request('POST',sample['endpoint'],payload);self.assertEqual(status,409)
            status,_=self.request('GET',result['evidence_file']);self.assertEqual(status,200)
    def test_invalid_examples_and_official_rejected(self):
        for sample in self.samples:
            payload=copy.deepcopy(sample['request'])
            if sample['metric_id']=='M03':payload['scenarios']=[]
            else:payload['counts'][sample['invalid_count_field']]=0
            status,raw=self.request('POST',sample['endpoint'],payload);body=json.loads(raw)
            self.assertEqual(status,422);self.assertIn('error',body);self.assertNotIn('score',body)
            payload=copy.deepcopy(sample['request']);payload['run_mode']='OFFICIAL'
            status,_=self.request('POST',sample['endpoint'],payload);self.assertEqual(status,422)
        self.assertFalse((self.root/'results/official').exists())

    def test_mock_generation_http(self):
        request=dict(business_unit_id='BU03',workflow_id='WF-001')
        status,raw=self.request('POST','/api/m03/generate',request)
        self.assertEqual(status,200);body=json.loads(raw)
        self.assertTrue(body['synthetic']);self.assertEqual(body['status'],'SUCCESS')
        self.assertEqual(self.request('POST','/api/m03/generate',request)[1],raw)
        self.assertEqual(self.request('POST','/api/m03/generate',dict(request,run_mode='OFFICIAL'))[0],422)
        self.assertEqual(self.request('POST','/api/m03/generate',dict(request,generator_mode='REAL'))[0],503)
